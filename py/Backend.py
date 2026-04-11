"""
Backend.py — ComfyUI-Photoshop plugin backend.
Bridges ComfyUI and Photoshop via WebSocket, supports multi-client
queued generation with directed image delivery. BY ：cdmusic2019 /cdmusic
对列操作有很多异常情况我可能还没有考虑到，如果有问题我有时间再修复。如果队列混乱了，把所有客户端重新加载就行了，服务端会自动清理！
"""

import os
import subprocess
import sys
import uuid
import json
import base64
import asyncio
import time
import aiohttp
from aiohttp import web, WSMsgType
import folder_paths
from server import PromptServer
import functools
import glob
# ──────────────────────────────────────────────
#  Paths
# ──────────────────────────────────────────────
nodepath = os.path.join(
    folder_paths.get_folder_paths("custom_nodes")[0],
    "comfyui-photoshop",
)
workflows_directory = os.path.join(nodepath, "data", "workflows")
ps_inputs_directory = os.path.join(nodepath, "data", "ps_inputs")

# ──────────────────────────────────────────────
#  Global state
# ──────────────────────────────────────────────
# Connected clients: {client_id: {"ws", "platform", "ip"}}
clients: dict = {}
photoshop_users: list = []
comfyui_users: list = []
# # 10分钟超时（设置单个任务总时长，超过踢出队列）
# 10-minute timeout (sets the total duration for a single task; tasks that time out will be removed from the queue).
GENERATION_TIMEOUT = 600  # 10分钟
generation_start_time: float = 0
QUICK_FAIL_TIMEOUT = 10  # prompt rapid loss
generation_started: bool = False  # True = ComfyUI 已发出 execution_start

# Generation queue (FIFO). Each element:
#   {"client_id": str, "data": dict, "prompt_id": str|None, "task_id": str|None}
ps_combinedData: list = []
current_generating_client_id: str | None = None
current_batch_total: int = 0
current_batch_sent: int = 0
current_task_id: str | None = None  # 新增：当前任务 ID
# Disconnected-client IP map (for reconnect matching)
disconnected_clients_ip: dict = {}

# Cancelled-task cooldown (prevents auto-rejoin after disconnect-cancel)
cancelled_task_ips: dict = {}       # {ip: timestamp}
CANCEL_COOLDOWN: int = 10           # seconds


# ComfyUI API base URL
COMFYUI_API_BASE = "http://127.0.0.1:8188"


# ──────────────────────────────────────────────
#  Render cache (in-memory image store)
# ──────────────────────────────────────────────
render_cache: dict = {}
render_cache_lock = asyncio.Lock()
RENDER_CACHE_MAX_SIZE = 20 * 1024 * 1024  # 20 MB


def _cache_size() -> int:
    return sum(len(v) for v in render_cache.values())


async def _check_and_clear_cache():
    if _cache_size() > RENDER_CACHE_MAX_SIZE:
        render_cache.clear()


# ──────────────────────────────────────────────
#  Utility helpers
# ──────────────────────────────────────────────
def force_pull():
    fetch = subprocess.run(["git", "fetch"], capture_output=True, text=True, cwd=nodepath)
    print(fetch.stdout)
    if fetch.returncode != 0:
        print(f"# PS: Fetch error: {fetch.stderr}")
        return
    reset = subprocess.run(
        ["git", "reset", "--hard", "origin/main"],
        capture_output=True, text=True, cwd=nodepath,
    )
    print(reset.stdout)
    if reset.returncode != 0:
        print(f"# PS: Reset error: {reset.stderr}")


def install_plugin():
    subprocess.run([sys.executable, os.path.join(nodepath, "Install_Plugin", "installer.py")])


async def save_file(data_b64: str, filename: str, client_id: str = None):
    prefix = f"{client_id}_" if client_id else ""
    actual_filename = f"{prefix}{filename}"
    filepath = os.path.join(ps_inputs_directory, actual_filename)
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(data_b64))


async def save_config(data: dict, client_id: str = None):
    prefix = f"{client_id}_" if client_id else ""
    actual_filename = f"{prefix}config.json"
    filepath = os.path.join(ps_inputs_directory, actual_filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ──────────────────────────────────────────────
#  WebSocket messaging
# ──────────────────────────────────────────────
async def send_message(users: list, msg_type: str | None = None, message=None):
    """Send to the *latest* user in a user list (legacy broadcast)."""
    try:
        if not users:
            return
        uid = users[-1]
        if uid in clients:
            ws = clients[uid]["ws"]
            payload = json.dumps({msg_type: message}) if msg_type else message
            await ws.send_str(payload)
        else:
            print(f"# PS: User {uid} not connected")
    except Exception as e:
        print(f"# PS: error send_message: {e}")


async def send_to_target_client(client_id: str, data) -> bool:
    """Send to a specific client. Returns True on success."""
    info = clients.get(client_id)
    if info:
        ws = info["ws"]
        if not ws.closed:
            await ws.send_str(data if isinstance(data, str) else json.dumps(data))
            return True
    return False


# ──────────────────────────────────────────────
#  IP-based pairing (PS ↔ ComfyUI on same host)
# ──────────────────────────────────────────────
def find_paired_comfyui_client(ps_client_id: str):
    ps_info = clients.get(ps_client_id)
    if not ps_info:
        return None
    ps_ip = ps_info.get("ip")
    for cm_id in comfyui_users:
        if cm_id in clients and clients[cm_id].get("ip") == ps_ip:
            return cm_id
    return None


async def send_to_paired_comfyui(ps_client_id: str, msg_type=None, message=None):
    paired = find_paired_comfyui_client(ps_client_id)
    if paired and paired in clients:
        ws = clients[paired]["ws"]
        payload = json.dumps({msg_type: message}) if msg_type else message
        await ws.send_str(payload)
        print(f"# PS: Sent to paired ComfyUI {paired} (same IP as {ps_client_id})")
    else:
        print(f"# PS: No paired ComfyUI for {ps_client_id}, broadcasting")
        await send_message(comfyui_users, msg_type, message)


# ──────────────────────────────────────────────
#  Queue management
# ──────────────────────────────────────────────
def is_client_in_queue(client_id: str) -> bool:
    return any(item["client_id"] == client_id for item in ps_combinedData)


def add_to_queue(client_id: str, data: dict) -> bool:
    if is_client_in_queue(client_id):
        print(f"# PS: Client {client_id} already in queue, ignoring")
        return False
    ps_combinedData.append({"client_id": client_id, "data": data, "prompt_id": None})
    print(f"# PS: Client {client_id} added to queue. Length: {len(ps_combinedData)}")
    return True


def remove_from_queue(client_id: str):
    global ps_combinedData
    ps_combinedData = [i for i in ps_combinedData if i["client_id"] != client_id]
    print(f"# PS: Client {client_id} removed from queue. Length: {len(ps_combinedData)}")


def get_queue_first():
    return ps_combinedData[0] if ps_combinedData else None


def pop_queue_first():
    if ps_combinedData:
        item = ps_combinedData.pop(0)
        print(f"# PS: Popped queue head: {item['client_id']}. Length: {len(ps_combinedData)}")
        return item
    return None


def find_client_by_ip(original_client_id: str):
    """Find a replacement client with the same IP (handles browser refresh)."""
    if clients.get(original_client_id):
        return original_client_id
    original_ip = disconnected_clients_ip.get(original_client_id)
    if not original_ip:
        return None
    for cid, info in clients.items():
        if (info.get("ip") == original_ip
                and info.get("platform") == "ps"
                and cid != original_client_id):
            print(f"# PS: Found replacement {cid} (same IP {original_ip})")
            return cid
    return None


# ──────────────────────────────────────────────
#  Shared delivery helpers (DRY)
# ──────────────────────────────────────────────
def _resolve_target_client(first: dict):
    """Return the actual target client_id or None. Updates *first* in-place
    if a refreshed client with the same IP is found."""
    target = first["client_id"]
    if target in clients:
        return target
    new_id = find_client_by_ip(target)
    if new_id and new_id in clients:
        first["client_id"] = new_id
        print(f"# PS: Redirecting to refreshed client {new_id}")
        return new_id
    print(f"# PS: Target {target} not found. Discarded.")
    return None


async def _send_to_client_ws(client_id: str, payload: str) -> bool:
    """Try sending via WebSocket. Returns True on success."""
    info = clients.get(client_id)
    if not info:
        return False
    ws = info["ws"]
    if ws.closed:
        print(f"# PS: Target {client_id} connection closed")
        return False
    try:
        await ws.send_str(payload)
        return True
    except Exception as e:
        print(f"# PS: Error sending to {client_id}: {e}")
        return False


async def _send_or_broadcast(msg_type: str, msg_data, description: str = "data"):
    """If the queue is active, send to the head client; otherwise broadcast.
    After sending, completes the queue head."""
    if not ps_combinedData:
        print(f"# PS: Queue empty, broadcasting {description}")
        await send_message(photoshop_users, msg_type, msg_data)
        return

    first = ps_combinedData[0]
    target = _resolve_target_client(first)
    if target:
        payload = json.dumps({msg_type: msg_data})
        ok = await _send_to_client_ws(target, payload)
        if ok:
            print(f"# PS: {description} sent to {target}")

    await _complete_queue_head()


async def _complete_queue_head():
    """Pop the finished queue head, reset batch counters, start next task."""
    global current_generating_client_id, current_batch_sent, current_batch_total
    global generation_start_time, generation_started 
    completed = ps_combinedData.pop(0)
    print(f"# PS: Removed {completed['client_id']} from queue. "
          f"Remaining: {len(ps_combinedData)}")
    current_generating_client_id = None
    current_batch_sent = 0
    current_batch_total = 0
    generation_start_time = 0  # ★ 
    generation_started = False  # ★ 重置
    # ★ 广播队列状态给所有客户端
    await broadcast_queue_status()

    if ps_combinedData:
        print(f"# PS: Starting next task for {ps_combinedData[0]['client_id']}")
        await start_next_generation()
    else:
        print("# PS: Queue is now empty")


# ──────────────────────────────────────────────
#  ComfyUI API calls
# ──────────────────────────────────────────────
async def cancel_comfyui_current_task():
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{COMFYUI_API_BASE}/interrupt") as r:
                print(f"# PS: Interrupted ComfyUI task, status: {r.status}")
    except Exception as e:
        print(f"# PS: Error interrupting: {e}")


async def cancel_comfyui_queued_task(prompt_id: str):
    if not prompt_id:
        return
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{COMFYUI_API_BASE}/queue", json={"delete": [prompt_id]}) as r:
                print(f"# PS: Cancelled queued task {prompt_id}, status: {r.status}")
    except Exception as e:
        print(f"# PS: Error cancelling queued task: {e}")


# ──────────────────────────────────────────────
#  Zombie / cancel cleanup
# ──────────────────────────────────────────────
async def cleanup_zombie_connections(new_client_id: str, client_ip: str, platform_type: str):
    """Remove same-IP, same-platform connections whose WebSocket is closed."""
    global current_generating_client_id
    zombie_ids = [
        cid for cid, info in clients.items()
        if (cid != new_client_id
            and info.get("ip") == client_ip
            and info.get("platform") == platform_type
            and (info.get("ws") is None or info["ws"].closed))
    ]
    if not zombie_ids:
        return

    print(f"# PS: Cleaning {len(zombie_ids)} zombie(s) for IP {client_ip}: {zombie_ids}")

    for zid in zombie_ids:
        zinfo = clients.get(zid)
        if not zinfo:
            continue
        zplat = zinfo.get("platform")

        if zplat == "ps":
            if zid in photoshop_users:
                photoshop_users.remove(zid)
            if is_client_in_queue(zid):
                first = get_queue_first()
                if first and first["client_id"] == zid:
                    # Transfer active task to new connection
                    first["client_id"] = new_client_id
                    if current_generating_client_id == zid:
                        current_generating_client_id = new_client_id
                    print(f"# PS: Transferred active task {zid} → {new_client_id}")
                else:
                    remove_from_queue(zid)
        elif zplat == "cm":
            if zid in comfyui_users:
                comfyui_users.remove(zid)

        clients.pop(zid, None)
        disconnected_clients_ip.pop(zid, None)
        print(f"# PS: Cleaned zombie {zid} ({zplat}, {client_ip})")


async def cleanup_cancelled_records():
    """Evict expired cancel-cooldown entries."""
    now = time.time()
    expired = [ip for ip, ts in cancelled_task_ips.items()
               if now - ts > CANCEL_COOLDOWN * 3]
    for ip in expired:
        del cancelled_task_ips[ip]

# ──────────────────────────────────────────────
#  对蒙片，图片等获取ID(Obtain ID from masks, images, etc.)
# ──────────────────────────────────────────────



@PromptServer.instance.routes.get("/ps/current_task")
async def get_current_task(request):
    """
    供 nodePlugin 查询当前任务信息
    Provides nodePlugin with information on the current task.
    """
    if current_generating_client_id and current_task_id:
        first = get_queue_first()
        return web.json_response({
            "client_id": current_generating_client_id,
            "task_id": current_task_id,
            "has_active_task": True,
            "batch_total": current_batch_total,
            "batch_sent": current_batch_sent,
            "prompt_id": first.get("prompt_id") if first else None
        })
    return web.json_response({
        "client_id": "",
        "task_id": "",
        "has_active_task": False,
        "batch_total": 0,
        "batch_sent": 0,
        "prompt_id": None
    })


@PromptServer.instance.routes.get("/ps/active_client_id")
async def get_active_client_id(request):
    
    # 1. Queue mode: Returns the currently generated client.
    if current_generating_client_id:
        return web.json_response({"client_id": current_generating_client_id})
    
    # 2. Single-user mode: Matching by IP
    request_ip = request.remote or request.headers.get("X-Forwarded-For", "unknown")
    for ps_id in photoshop_users:
        if clients.get(ps_id, {}).get("ip") == request_ip:
            return web.json_response({"client_id": ps_id})
    
    # 3. 无匹配
    return web.json_response({"client_id": ""})
# ──────────────────────────────────────────────
#  HTTP routes – render binary / cache
# ──────────────────────────────────────────────
@PromptServer.instance.routes.post("/ps/render_binary")
async def render_binary(request):
    global render_cache, current_batch_sent
    try:
        idx = int(request.headers.get("X-Image-Index", "0"))
        count = int(request.headers.get("X-Image-Count", "1"))
        filename = request.headers.get("X-Filename", f"render_{idx}.png")
        data = await request.read()
        async with render_cache_lock:
            if idx == 0:
                await _check_and_clear_cache()
            render_cache[filename] = data
        
        current_batch_sent = idx + 1
        
        # Last image of the batch
        if idx == count - 1:
            files = [f"render_{i}.png" for i in range(count)]
            
            if ps_combinedData:
                first = ps_combinedData[0]
                target = _resolve_target_client(first)
                if target:
                    payload = json.dumps({"renders_ready": {"count": count, "files": files}})
                    ok = await _send_to_client_ws(target, payload)
                    if ok:
                        print(f"# PS: renders_ready ({count} images) sent to {target}")
              
                await _complete_queue_head()
            else:
                print(f"# PS: Queue empty, broadcasting renders_ready ({count} images)")
                await send_message(photoshop_users, "renders_ready", {"count": count, "files": files})
        
        return web.json_response({"success": True, "index": idx, "count": count})
    except Exception as e:
        print(f"# PS: Render binary error: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


@PromptServer.instance.routes.get("/ps/get_render/{filename}")
async def get_render(request):
    try:
        filename = request.match_info["filename"]
        async with render_cache_lock:
            if filename in render_cache:
                data = render_cache[filename]
                print(f"# PS: Serving from cache: {filename} ({len(data)} bytes)")
                return web.Response(body=data, content_type="image/png")
            print(f"# PS: Not in cache: {filename} (keys: {list(render_cache.keys())})")
            return web.json_response({"error": "Not found"}, status=404)
    except Exception as e:
        print(f"# PS: Get render error: {e}")
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.post("/ps/clear_render_cache")
async def clear_render_cache(request):
    async with render_cache_lock:
        n = len(render_cache)
        render_cache.clear()
    print(f"# PS: Cleared {n} cached items")
    return web.json_response({"success": True, "cleared": n})


# ──────────────────────────────────────────────
#  HTTP routes – render (JSON / base64 mode)
# ──────────────────────────────────────────────
@PromptServer.instance.routes.post("/ps/render")
async def render_handler(request):
    try:
        data = await request.json()
        images = data.get("images", [])
        if not images:
            return web.Response(text="No images provided", status=400)

        if data.get("multi") and len(images) > 1:
            msg_type, msg_data = "renders", json.dumps(images)
        else:
            msg_type, msg_data = "render", images[0]

        await _send_or_broadcast(msg_type, msg_data, description="rendered image(s)")
        return web.Response(text="OK")
    except Exception as e:
        print(f"# PS: render_handler error: {e}")
        return web.Response(text=str(e), status=500)


@PromptServer.instance.routes.post("/ps/renders")
async def send_renders(request):
    try:
        paths = (await request.json()).get("images", [])
        encoded = []
        for p in paths[:9]:
            with open(p, "rb") as f:
                encoded.append(base64.b64encode(f.read()).decode("utf-8"))

        await _send_or_broadcast("renders", json.dumps(encoded), description="renders")
    except Exception as e:
        print(f"# PS: send_renders error: {e}")
    return web.Response(text="Renders sent to PS")


# ──────────────────────────────────────────────
#  HTTP routes – upload / file serving
# ──────────────────────────────────────────────
@PromptServer.instance.routes.post("/ps/upload_canvas_binary")
async def upload_canvas_binary(request):
    try:
        os.makedirs(ps_inputs_directory, exist_ok=True)
        filename = request.headers.get("X-Filename", "PS_canvas.png")
        
        # Try to get the clientId from the request
        client_id = request.headers.get("X-Client-Id") or request.query.get("clientId", "")
        
        #  The IP address will automatically match the corresponding PS client ID.
        if not client_id:
            client_ip = request.remote or request.headers.get("X-Forwarded-For", "unknown")
            
            matching_clients = [cid for cid in photoshop_users if clients.get(cid, {}).get("ip") == client_ip]           
            if matching_clients:                
                client_id = matching_clients[-1]
                print(f"# PS: Auto-matched HTTP upload to client {client_id} via IP {client_ip}")

        # Concatenate filenames with client prefix
        prefix = f"{client_id}_" if client_id else ""
        actual_filename = f"{prefix}{filename}"
        filepath = os.path.join(ps_inputs_directory, actual_filename)
        
        data = await request.read()
        print(f"# PS: Received binary data for {actual_filename}, size: {len(data)} bytes")
        with open(filepath, "wb") as f:
            f.write(data)
            
        return web.json_response({"success": True, "filename": actual_filename, "size": len(data)})
    except Exception as e:
        print(f"# PS: Upload error: {e}")
        import traceback; traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)}, status=500)


@PromptServer.instance.routes.get("/ps/workflows/{name:.+}")
async def get_workflow(request):
    file = os.path.abspath(
        os.path.join(workflows_directory, request.match_info["name"] + ".json")
    )
    if os.path.commonpath([file, workflows_directory]) != workflows_directory:
        return web.Response(status=403)
    return web.FileResponse(file)


@PromptServer.instance.routes.get("/ps/inputs/{filename}")
async def get_input_file(request):
    file = os.path.abspath(
        os.path.join(ps_inputs_directory, request.match_info["filename"])
    )
    if os.path.commonpath([file, ps_inputs_directory]) != ps_inputs_directory:
        return web.Response(status=403)
    return web.FileResponse(file)

@PromptServer.instance.routes.get("/ps/paired_client_id")
async def get_paired_client_id(request):
    cm_client_id = request.query.get("clientId")
    
    # 1. Try using the websocket clientId to find a PS client with the same IP address.
    if cm_client_id and cm_client_id in clients:
        cm_ip = clients[cm_client_id].get("ip")
        for ps_id in photoshop_users:
            if clients.get(ps_id, {}).get("ip") == cm_ip:
                return web.json_response({"ps_client_id": ps_id})
                
    # 2. Try matching the IP address of the HTTP request.
    client_ip = request.remote or request.headers.get("X-Forwarded-For", "unknown")
    for ps_id in photoshop_users:
        if clients.get(ps_id, {}).get("ip") == client_ip:
            return web.json_response({"ps_client_id": ps_id})
            
    # 3. Downgrade, revert to single-user mode.
    active_client_file = os.path.join(ps_inputs_directory, "active_client.txt")
    if os.path.exists(active_client_file):
        try:
            with open(active_client_file, "r") as f:
                return web.json_response({"ps_client_id": f.read().strip()})
        except:
            pass
            
    return web.json_response({"ps_client_id": ""})

# ──────────────────────────────────────────────
#  WebSocket handler
# ──────────────────────────────────────────────
@PromptServer.instance.routes.get("/ps/ws")
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_id = request.query.get("clientId", str(uuid.uuid4()))
    platform = request.query.get("platform", "unknown")
    client_ip = request.remote or request.headers.get("X-Forwarded-For", "unknown")
    await cleanup_zombie_connections(client_id, client_ip, platform)
    clients[client_id] = {"ws": ws, "platform": platform, "ip": client_ip}
    if platform == "ps":
        photoshop_users.append(client_id)
        print(f"# PS: {client_id} Photoshop Connected (IP: {client_ip})")
        await send_message(comfyui_users, "photoshopConnected")
        await handle_client_reconnect(client_id, client_ip)

        # ★ Broadcast the current queue status when a new client connects.
        await broadcast_queue_status()

    elif platform == "cm":
        comfyui_users.append(client_id)
        if photoshop_users:
            await send_message(comfyui_users, "photoshopConnected")
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            await handle_message(client_id, platform, msg.data)
        elif msg.type == WSMsgType.ERROR:
            print(f"# PS: WS error {client_id}: {ws.exception()}")
    await handle_disconnect(client_id, platform)
    return ws


# ──────────────────────────────────────────────
#  Reconnect / disconnect
# ──────────────────────────────────────────────
async def handle_client_reconnect(new_client_id: str, client_ip: str):
    global current_generating_client_id

    # Cooldown check: task was cancelled recently for this IP
    if client_ip in cancelled_task_ips:
        elapsed = time.time() - cancelled_task_ips[client_ip]
        cancelled_task_ips.pop(client_ip, None)
        if elapsed < CANCEL_COOLDOWN:
            print(f"# PS: {client_ip} in cancel cooldown ({elapsed:.1f}s), skipping rejoin")
            return

    # Normal refresh: swap old → new ID in queue
    for item in ps_combinedData:
        old_id = item["client_id"]
        if old_id != new_client_id and old_id not in clients:
            if disconnected_clients_ip.get(old_id) == client_ip:
                print(f"# PS: Reconnect: replacing {old_id} → {new_client_id}")
                item["client_id"] = new_client_id
                if current_generating_client_id == old_id:
                    current_generating_client_id = new_client_id
                disconnected_clients_ip.pop(old_id, None)
                break


async def handle_disconnect(client_id: str, platform: str):
    if platform == "ps":
        client_ip = clients.get(client_id, {}).get("ip")
        if client_ip:
            disconnected_clients_ip[client_id] = client_ip
        if client_id in photoshop_users:
            photoshop_users.remove(client_id)
        was_in_queue = is_client_in_queue(client_id)
        await handle_cancel_task(client_id)
        if was_in_queue and client_ip:
            cancelled_task_ips[client_ip] = time.time()
            print(f"# PS: Recorded cancelled IP: {client_ip}")
        print(f"# PS: {client_id} Photoshop Disconnected")
        if not photoshop_users:
            await send_message(comfyui_users, "photoshopDisconnected")

        # ★ Disconnected broadcast queue status
        await broadcast_queue_status()
        cleanup_client_files(client_id)

    elif platform == "cm":
        if client_id in comfyui_users:
            comfyui_users.remove(client_id)
    clients.pop(client_id, None)

async def _handle_generation_interrupted(msg: dict, interrupt_key: str):
    """
    Handle ComfyUI task interruption or error.
    Removes the currently generating client from ps_combinedData,
    notifies that client, broadcasts updated queue status,
    and starts the next queued task if any.
    """
    global current_generating_client_id, current_batch_sent, current_batch_total
    global generation_start_time, generation_started  

    if not current_generating_client_id:
        print(f"# PS: Interrupted but no active generation client, ignoring")
        # Still forward the message to all PS clients
        await send_message(photoshop_users, "", json.dumps(msg))
        return

    interrupted_client_id = current_generating_client_id
    print(f"# PS: Repetitive tasks {interrupted_client_id} "
          f"(reason: {interrupt_key})")

    # 1. Notify the interrupted client
    if interrupted_client_id in clients:
        try:
            error_detail = msg.get(interrupt_key, "Task was interrupted or failed")
            await _send_to_client_ws(interrupted_client_id, json.dumps({
                "type": "generationInterrupted",
                "reason": interrupt_key,
                "detail": error_detail if isinstance(error_detail, str) else json.dumps(error_detail),
                "message": "Your generation task was interrupted.",
            }))
        except Exception as e:
            print(f"# PS: Error notifying interrupted client: {e}")

    # 2. Remove the interrupted client from the queue head
    if ps_combinedData and ps_combinedData[0]["client_id"] == interrupted_client_id:
        removed = ps_combinedData.pop(0)
        print(f"# PS: Removed interrupted client {removed['client_id']} from queue. "
              f"Remaining: {len(ps_combinedData)}")
    elif is_client_in_queue(interrupted_client_id):
        # Edge case: client is in queue but not at the head
        remove_from_queue(interrupted_client_id)
    else:
        print(f"# PS: Interrupted client {interrupted_client_id} was not in queue")

    # 3. Reset generation state
    current_generating_client_id = None
    current_batch_sent = 0
    current_batch_total = 0
    generation_start_time = 0  # ★ 
    generation_started = False  # ★ 重置

    # 4. Broadcast updated queue status to all clients
    await broadcast_queue_status()

    # 5. Start the next task in the queue if any
    if ps_combinedData:
        print(f"# PS: Starting next task for {ps_combinedData[0]['client_id']}")
        await start_next_generation()
    else:
        print("# PS: Queue is now empty after interruption")



# ──────────────────────────────────────────────
#  Message handling
# ──────────────────────────────────────────────
_PROGRESS_KEYS = frozenset([
    "progress", "generating", "render_status",
    "execution_progress", "execution_start", "execution_complete",
])

# ComfyUI 任务异常/中断事件的 key
_INTERRUPT_KEYS = frozenset([
    "execution_interrupted",
    "execution_error",
    "execution_cached",      
    "prompt_outputs_failed_validation",  
    "invalid_prompt",                    
])


async def handle_message(client_id: str, platform: str, data: str):
    global current_generating_client_id, current_batch_total, current_batch_sent
    msg = json.loads(data)

    if platform == "cm":
        try:
            if "pullupdate" in msg:
                await send_message(comfyui_users, "alert",
                                   "Updating, please restart ComfyUI after update")
                force_pull()
            elif "install_plugin" in msg:
                install_plugin()

            # ★ Detecting abnormal interruption or termination of ComfyUI tasks by the user.
            elif msg.keys() & _INTERRUPT_KEYS:
                interrupted_key = (msg.keys() & _INTERRUPT_KEYS).pop()
                print(f"# PS: ComfyUI task interrupted/error detected: {interrupted_key}")
                await _handle_generation_interrupted(msg, interrupted_key)

            elif msg.keys() & _PROGRESS_KEYS and current_generating_client_id:
                # Directed progress → only to the generating client
                if current_generating_client_id in clients:
                    await _send_to_client_ws(current_generating_client_id, json.dumps(msg))
                else:
                    print(f"# PS: Generating client {current_generating_client_id} gone, "
                          f"progress discarded")
            else:
                await send_message(photoshop_users, "", json.dumps(msg))
        except Exception as e:
            print(f"# PS: error from ComfyUI: {e}")

    elif platform == "ps":
        try:
            if msg.get("queue") is True:
                await handle_ps_generate_request(client_id, msg)
            elif "cancelTask" in msg:
                await handle_cancel_task(client_id)
            elif not (msg.keys() & {"configdata", "maskBase64", "canvasBase64",
                                     "workspace", "queue", "cancelTask"}):
                await send_to_paired_comfyui(client_id, "", json.dumps(msg))
        except Exception as e:
            print(f"# PS: error from Photoshop: {e}")


# ──────────────────────────────────────────────
#  Generate request / cancel / forward
# ──────────────────────────────────────────────
async def handle_ps_generate_request(client_id: str, msg: dict):
    # Dedup
    if is_client_in_queue(client_id):
        print(f"# PS: Duplicate request from {client_id} ignored")
        pos = next((i + 1 for i, it in enumerate(ps_combinedData)
                     if it["client_id"] == client_id), -1)
        await send_to_target_client(client_id, json.dumps({
            "type": "queueStatus",
            "message": "Already in queue. Please wait.",
            "position": pos,
        }))
        return
    if not add_to_queue(client_id, msg):
        return

    # ★ 广播队列状态给所有客户端
    await broadcast_queue_status()

    pos = len(ps_combinedData)
    await send_to_target_client(client_id, json.dumps({
        "type": "queueStatus",
        "message": f"You are number {pos} in the queue.",
        "position": pos,
    }))
    if len(ps_combinedData) == 1:
        await process_and_forward_to_comfyui(msg)


async def process_and_forward_to_comfyui(msg: dict):
    global current_generating_client_id, current_batch_total, current_batch_sent
    global generation_start_time, generation_started
    first = get_queue_first()
    if not first:
        return

    client_id = first["client_id"]
    current_generating_client_id = client_id
    current_batch_sent = 0
    current_batch_total = msg.get("batch_size", 1)
    generation_start_time = time.time()  # ★ Start time
    generation_started = False 
    task_id = str(uuid.uuid4())
    first["task_id"] = task_id
    print(f"# PS: Starting generation for {client_id}, task_id: {task_id}")

    try:
        # ★ 记录当前正在生成的客户端ID供Node读取
        active_client_file = os.path.join(ps_inputs_directory, "active_client.txt")
        with open(active_client_file, "w") as f:
            f.write(client_id)

        if msg.get("canvasBase64"):
            await save_file(msg["canvasBase64"], "PS_canvas.png", client_id)
        if msg.get("maskBase64"):
            await save_file(msg["maskBase64"], "PS_mask.png", client_id)
        if msg.get("configdata"):
            cfg = msg["configdata"]
            if isinstance(cfg, str):
                cfg = json.loads(cfg)
            await save_config(cfg, client_id)

        await send_to_paired_comfyui(
            client_id, "", json.dumps({"queue": True, "task_id": task_id})
       )
       # ★ Start fast failure detection
        asyncio.ensure_future(_quick_fail_check(client_id, task_id)) 
    except Exception as e:
        print(f"# PS: Error processing combinedData: {e}")


async def _quick_fail_check(client_id: str, task_id: str):
    """
    在发送 queue 指令后等待 3 秒，
    检测任务是否正常进行或已完成。
    如果 ComfyUI 没有运行中的任务，且客户端仍在队列头部，
    则认为是异常情况，需要移除客户端。
    After sending the queue command, wait 3 seconds,
    and check if the task is progressing normally or has been completed.
    If ComfyUI has no running tasks and the client is still at the head of the queue,
    this is considered an abnormal situation, and the client needs to be removed.
    """
    global generation_started
    
    # 等待 3 秒后检测
    await asyncio.sleep(3)
    
    # Check if the current client is still at the head of the queue and is a client that is being generated.
    first = get_queue_first()
    if not first:
        print(f"# PS: [QuickFail] Queue is empty, task for {client_id} already completed")
        return
    
    if first["client_id"] != client_id or first.get("task_id") != task_id:    
        print(f"# PS: [QuickFail] Client {client_id} no longer at queue head, skipping")
        return
    
    if current_generating_client_id != client_id:
        
        print(f"# PS: [QuickFail] Current generating client changed, skipping")
        return
    
    # If the image has already been sent, it means the task has been completed but the queue has not been cleared (an anomaly).
    if current_batch_sent > 0:
        print(f"# PS: [QuickFail] Images already sent ({current_batch_sent}), "
              f"forcing queue cleanup for {client_id}")
        await _complete_queue_head()
        return
    
    # Check if ComfyUI has any running tasks.
    has_running_task = await _check_comfyui_running_tasks()
    
    if has_running_task:
        
        print(f"# PS: [QuickFail] ComfyUI has running tasks, "
              f"generation for {client_id} is proceeding normally")
        return
    
    # There are no running tasks, the client is still at the head of the queue, and no images have been sent.
    # In abnormal situations, the client needs to be removed.
    print(f"# PS: [QuickFail] No running tasks in ComfyUI, no images sent, "
          f"client {client_id} still at queue head after 3s, removing")
    
    await _handle_generation_interrupted(
        {"event": "quick_fail_timeout", "data": {"reason": "no_running_tasks_detected"}},
        "quick_fail_timeout"
    )

async def _check_comfyui_running_tasks() -> bool:
    """
    Check if there are any running tasks.
    Returning True indicates that there are running tasks.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{COMFYUI_API_BASE}/queue", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    queue_data = await response.json()
                    
                    running = queue_data.get("queue_running", [])
                    if running and len(running) > 0:
                        print(f"# PS: [QueueCheck] ComfyUI has {len(running)} running task(s)")
                        return True
                    else:
                        print(f"# PS: [QueueCheck] ComfyUI has no running tasks")
                        return False
                else:
                    print(f"# PS: [QueueCheck] Failed to query ComfyUI queue, status: {response.status}")
                   
                    return True
    except asyncio.TimeoutError:
        print(f"# PS: [QueueCheck] Timeout querying ComfyUI queue")
        return True
    except Exception as e:
        print(f"# PS: [QueueCheck] Error querying ComfyUI queue: {e}")        
        return True





async def start_next_generation():
    first = get_queue_first()
    if not first:
        print("# PS: Queue empty, nothing to generate.")
        return
    await process_and_forward_to_comfyui(first["data"])


async def handle_cancel_task(client_id: str):
    global current_generating_client_id
    if not is_client_in_queue(client_id):
        print(f"# PS: {client_id} not in queue, nothing to cancel")
        return

    first = get_queue_first()
    if first and first["client_id"] == client_id:
        # The task being generated was cancelled
        prompt_id = first.get("prompt_id")
        if prompt_id:
            await cancel_comfyui_queued_task(prompt_id)
        await cancel_comfyui_current_task()
        ps_combinedData.pop(0)
        current_generating_client_id = None

        # ★ Broadcast queue status
        await broadcast_queue_status()

        if ps_combinedData:
            await start_next_generation()
    else:
        # The queued task was cancelled.
        remove_from_queue(client_id)

        # ★ Broadcast queue status
        await broadcast_queue_status()

    print(f"# PS: Task cancelled for {client_id}. Queue: {len(ps_combinedData)}")


# ──────────────────────────────────────────────
#  Queue sending and broadcasting/广播当前所有队列，显示在PS插件面版的render旁的 “q:0”处。
# ──────────────────────────────────────────────
async def broadcast_queue_status():
    """Queue broadcast"""
    total = len(ps_combinedData)
    for cid in photoshop_users:
        if cid not in clients:
            continue
        position = -1
        for idx, item in enumerate(ps_combinedData):
            if item["client_id"] == cid:
                position = idx
                break
        if position >= 0:
            wait_count = position
            is_generating = (position == 0 and current_generating_client_id == cid)
            msg = {
                "queueBroadcast": {
                    "total": total,
                    "inQueue": True,
                    "waitCount": wait_count,
                    "position": position + 1,
                    "isGenerating": is_generating,
                }
            }
        else:
            msg = {
                "queueBroadcast": {
                    "total": total,
                    "inQueue": False,
                    "waitCount": total,
                    "position": 0,
                    "isGenerating": False,
                }
            }
        try:
            ws = clients[cid]["ws"]
            if not ws.closed:
                await ws.send_str(json.dumps(msg))
        except Exception as e:
            print(f"# PS: Error broadcasting queue to {cid}: {e}")
    print(f"# PS: Queue broadcast sent. Total: {total}, clients: {len(photoshop_users)}")




# 文件清理函数,用来清理多客户端上传的画布，蒙版和配置文件（File cleanup）

def cleanup_client_files(client_id: str):
    
    files_to_delete = [
        f"{client_id}_PS_canvas.png",
        f"{client_id}_PS_mask.png",
        f"{client_id}_config.json"
    ]
    for filename in files_to_delete:
        filepath = os.path.join(ps_inputs_directory, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                # print(f"# PS: Deleted client file {filename}")
            except Exception as e:
                print(f"# PS: Failed to delete {filename}: {e}")

def cleanup_stale_client_files():
    """
    Clean up files left over from system crashes
    """
    if not os.path.exists(ps_inputs_directory):
        return

    
    active_client_ids = set(clients.keys())

    search_pattern = os.path.join(ps_inputs_directory, "client-*")
    cleaned_count = 0

    for file_path in glob.glob(search_pattern):
        filename = os.path.basename(file_path)       
        parts = filename.split('_', 1)
        if len(parts) >= 2:
            client_id = parts[0]
            if client_id not in active_client_ids:
                try:
                    os.remove(file_path)
                    cleaned_count += 1
                    print(f"# PS: Cleaned stale file: {filename}")
                except Exception as e:
                    print(f"# PS: Failed to delete {filename}: {e}")

    if cleaned_count > 0:
        print(f"# PS: Startup cleanup completed. "
              f"Removed {cleaned_count} stale client file(s).")
    else:
        print("# PS: Startup cleanup: No stale client files found.")


# ──────────────────────────────────────────────
#  Hook: Intercept ComfyUI execution events
# ──────────────────────────────────────────────
_original_send_sync = PromptServer.instance.send_sync

def _hooked_send_sync(event, data, sid=None):
    """Intercept ComfyUI native events for interrupt/error/validation detection."""
    global generation_started 
    result = _original_send_sync(event, data, sid)

    # List of events that need to be cleared from the queue
    cleanup_events = {
        "execution_interrupted",
        "execution_error",
    }

    if event in cleanup_events:
        print(f"# PS: [Hook] ComfyUI event '{event}' detected, "
              f"cleaning up queue for client: {current_generating_client_id}")
        try:
            asyncio.ensure_future(
                _handle_generation_interrupted(
                    {"event": event, "data": data}, event
                )
            )
        except Exception as e:
            print(f"# PS: [Hook] Error handling {event}: {e}")

    # 捕获 prompt 验证失败
    if event == "execution_start":
        generation_started = True
        print(f"# PS: [Hook] execution_start detected, generation_started = True")

    return result

PromptServer.instance.send_sync = _hooked_send_sync
print("# PS: Hooked into PromptServer.send_sync for interrupt/error detection")

#Clean up client files left behind when ComfyUI crashes.
cleanup_stale_client_files() 


async def _check_generation_timeout():
    global current_generating_client_id, generation_start_time
    while True:
        await asyncio.sleep(5)  # 每5秒检查一次
        if not current_generating_client_id or not generation_start_time:
            continue
        elapsed = time.time() - generation_start_time
        if elapsed > GENERATION_TIMEOUT:
            print(f"# PS: [Timeout] Generation for {current_generating_client_id} "
                  f"timed out after {elapsed:.0f}s, force removing from queue")
            
            # Get the prompt_id of the current task to cancel the task in the queue.
            first = get_queue_first()
            if first:
                prompt_id = first.get("prompt_id")
                if prompt_id:
                    await cancel_comfyui_queued_task(prompt_id)
            
            # Force interrupt the currently executing task in ComfyUI
            await cancel_comfyui_current_task()
            
            # Handle the interruption, remove the client, and start the next task.
            await _handle_generation_interrupted(
                {"event": "generation_timeout",
                 "data": {"elapsed": elapsed}},
                "generation_timeout"
            )


asyncio.ensure_future(_check_generation_timeout())



