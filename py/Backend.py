import os
import platform
import subprocess
import sys
import uuid
import json
import base64
import asyncio
from aiohttp import web, WSMsgType
import folder_paths
from aiohttp import web, WSMsgType
from server import PromptServer
from aiohttp import web

# Add a global dictionary to cache rendered images.
render_cache = {}  # 存储格式: {"render_0.png": bytes_data, ...}
render_cache_lock = asyncio.Lock()  # Asynchronous locks prevent concurrency issues.
RENDER_CACHE_MAX_SIZE = 20 * 1024 * 1024  # 20MB

def get_cache_size():
    """Calculate the current total cache size"""
    return sum(len(data) for data in render_cache.values())

async def check_and_clear_cache():
    """Check cache size and clear it if it exceeds 20MB."""
    global render_cache
    cache_size = get_cache_size()
    if cache_size > RENDER_CACHE_MAX_SIZE:
        print(f"# PS: Cache size {cache_size / 1024 / 1024:.2f}MB > 20MB, clearing...")
        render_cache.clear()
        return True
    return False


@PromptServer.instance.routes.post("/ps/render_binary")
async def render_binary(request):
    global render_cache
    try:
        image_index = int(request.headers.get('X-Image-Index', '0'))
        image_count = int(request.headers.get('X-Image-Count', '1'))
        filename = request.headers.get('X-Filename', f'render_{image_index}.png')
        
        data = await request.read()
        print(f"# PS: Received binary {filename} ({len(data)} bytes) [{image_index+1}/{image_count}]")
        
        async with render_cache_lock:
            #Detect the first image
            if image_index == 0:
                await check_and_clear_cache()
            
            render_cache[filename] = data
            
           
            current_size = get_cache_size()
            print(f"# PS: Cache size: {current_size / 1024 / 1024:.2f}MB")
        
        if image_index == image_count - 1:
            await send_message(photoshop_users, "renders_ready", {
                "count": image_count,
                "files": [f"render_{i}.png" for i in range(image_count)]
            })
        
        return web.json_response({
            "success": True,
            "index": image_index,
            "count": image_count
        })
        
    except Exception as e:
        print(f"# PS: Render binary error: {e}")
        return web.json_response({"success": False, "error": str(e)}, status=500)


# PS reads files from memory
@PromptServer.instance.routes.get("/ps/get_render/{filename}")
async def get_render(request):
    global render_cache
    try:
        filename = request.match_info['filename']
        
        print(f"# PS: Get render request: {filename}")
        
        async with render_cache_lock:
            if filename in render_cache:
                data = render_cache[filename]
                print(f"# PS: Serving from cache: {filename} ({len(data)} bytes)")
                return web.Response(
                    body=data,
                    content_type='image/png'
                )
            else:
                print(f"# PS: Not found in cache: {filename}")
                print(f"# PS: Available keys: {list(render_cache.keys())}")
                return web.json_response({"error": "File not found in cache"}, status=404)
            
    except Exception as e:
        print(f"# PS: Get render error: {e}")
        return web.json_response({"error": str(e)}, status=500)


# Clear cache endpoints
@PromptServer.instance.routes.post("/ps/clear_render_cache")
async def clear_render_cache(request):
    global render_cache
    async with render_cache_lock:
        count = len(render_cache)
        render_cache.clear()
    print(f"# PS: Cleared {count} items from render cache")
    return web.json_response({"success": True, "cleared": count})




# ComfyUI to PS routing（COMFYUI TO PS）
@PromptServer.instance.routes.post("/ps/render")
async def render_handler(request):
    """Process the rendered images sent from the node."""
    try:
        data = await request.json()
        images = data.get("images", [])
        is_multi = data.get("multi", False)
        
        if not images:
            return web.Response(text="No images provided", status=400)
        
        if is_multi and len(images) > 1:
            # Multiple images - Send "renders" message
            await send_message(photoshop_users, "renders", json.dumps(images))
        else:
            # Single image - Send "render" message (for compatibility)
            await send_message(photoshop_users, "render", images[0])
        
        return web.Response(text="OK")
    except Exception as e:
        print(f"# PS: Error in render_handler: {e}")
        return web.Response(text=str(e), status=500)

# ps_inputs_directory = os.path.join(nodepath, "data", "ps_inputs")

# Add an HTTP upload endpoint (ps to  comfyui)
@PromptServer.instance.routes.post("/ps/upload_canvas_binary")
async def upload_canvas_binary(request):
    try:
        
        os.makedirs(ps_inputs_directory, exist_ok=True)
        
     
        filename = request.headers.get('X-Filename', 'PS_canvas.png')
        filepath = os.path.join(ps_inputs_directory, filename)
        
        # Read binary data directly
        data = await request.read()
        
        print(f"# PS: Received binary data, size: {len(data)} bytes")
        
        # 写入文件
        with open(filepath, 'wb') as f:
            f.write(data)
        
        file_size = os.path.getsize(filepath)
        print(f"# PS: Canvas saved: {filepath} ({file_size} bytes)")
        
        return web.json_response({
            "success": True,
            "filename": filename,
            "size": file_size
        })
        
    except Exception as e:
        print(f"# PS: Upload error: {e}")
        import traceback
        traceback.print_exc()
        return web.json_response({"success": False, "error": str(e)}, status=500)



# Set up paths
nodepath = os.path.join(
    folder_paths.get_folder_paths("custom_nodes")[0],
    "comfyui-photoshop",
)
workflows_directory = os.path.join(nodepath, "data", "workflows")
ps_inputs_directory = os.path.join(
    folder_paths.get_folder_paths("custom_nodes")[0],
    "comfyui-photoshop",
    "data",
    "ps_inputs",
)

clients = {}
photoshop_users = []
comfyui_users = []


# Utility functions
def force_pull():
    fetch_result = subprocess.run(
        ["git", "fetch"], capture_output=True, text=True, cwd=nodepath
    )
    print(fetch_result.stdout)
    if fetch_result.returncode != 0:
        print(f"# PS: Fetch error: {fetch_result.stderr}")
        return

    reset_result = subprocess.run(
        ["git", "reset", "--hard", "origin/main"],
        capture_output=True,
        text=True,
        cwd=nodepath,
    )
    print(reset_result.stdout)
    if reset_result.returncode != 0:
        print(f"# PS: Reset error: {reset_result.stderr}")
        return


def install_plugin():
    installer_path = os.path.join(nodepath, "Install_Plugin", "installer.py")
    subprocess.run([sys.executable, installer_path])


async def save_file(data, filename):
    data = base64.b64decode(data)
    with open(os.path.join(ps_inputs_directory, filename), "wb") as file:
        file.write(data)


async def save_config(data):
    with open(
        os.path.join(ps_inputs_directory, "config.json"),
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(data, file, ensure_ascii=False)


async def send_message(users, type, message=True):
    try:
        if not users:
            print("# PS: PS not connected")
            return "PS not connected"

        latest_user = users[-1]
        if latest_user in clients:
            ws = clients[latest_user]["ws"]
            data = json.dumps({type: message}) if type else message
            await ws.send_str(data)
        else:
            print(f"# PS: User {latest_user} not connected")
    except Exception as e:
        print(f"# PS: error send_message: {e}")


# Websocket handler
@PromptServer.instance.routes.get("/ps/ws")
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    client_id = request.query.get("clientId", str(uuid.uuid4()))
    platform = request.query.get("platform", "unknown")
    clients[client_id] = {"ws": ws, "platform": platform}

    if platform == "ps":
        photoshop_users.append(client_id)
        print(f"# PS: {client_id} Photoshop Connected")
        await send_message(comfyui_users, "photoshopConnected")

    elif platform == "cm":
        comfyui_users.append(client_id)
        if len(photoshop_users) > 0:
            await send_message(comfyui_users, "photoshopConnected")

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            await handle_message(client_id, platform, msg.data)
        elif msg.type == WSMsgType.ERROR:
            print(f"# PS: Connection error from client {client_id}: {ws.exception()}")

    await handle_disconnect(client_id, platform)
    return ws


async def handle_message(client_id, platform, data):
    msg = json.loads(data)

    if platform == "cm":
        try:
            if "pullupdate" in msg:
                await send_message(
                    comfyui_users,
                    "alert",
                    "Updating, please Restart comfyui after update",
                )
                force_pull()
            elif "install_plugin" in msg:
                result = install_plugin()
                if result:
                    await send_message(comfyui_users, "alert", result)
            else:
                await send_message(photoshop_users, "", json.dumps(msg))
        except Exception as e:
            print(f"# PS: error fromComfyui: {e}")

    elif platform == "ps":
        try:
             # Add file upload method               
            if "canvasBase64" in msg and msg["canvasBase64"] is not None:
                canvas_data = msg["canvasBase64"]
                if canvas_data != "HTTP_UPLOADED" and canvas_data:
                    await save_file(canvas_data, "PS_canvas.png")
            if "maskBase64" in msg:
                await save_file(msg["maskBase64"], "PS_mask.png")
            if "configdata" in msg:
                await save_config(msg["configdata"])
            if "workspace" in msg:
                await send_message(comfyui_users, "workspace", msg["workspace"])

            # بررسی وجود کلید queue
            if "queue" in msg and msg["queue"]:
                # در نهایت ارسال پیام queue به سمت comfyui
                await send_message(comfyui_users, "queue", msg["queue"])

            # سایر پیام‌های معمولی که کلید خاصی ندارند
            if not any(
                key in msg
                for key in [
                    "configdata",
                    "maskBase64",
                    "canvasBase64",
                    "workspace",
                    "queue",
                ]
            ):
                await send_message(comfyui_users, "", json.dumps(msg))
        except Exception as e:
            print(f"# PS: error fromComfyui: {e}")


async def handle_disconnect(client_id, platform):
    del clients[client_id]
    if platform == "ps":
        photoshop_users.remove(client_id)
        print(f"# PS: User {client_id} disconnected from Photoshop (ps)")
    elif platform == "cm":
        comfyui_users.remove(client_id)
        print(f"# PS: User {client_id} disconnected from ComfyUI (cm)")


@PromptServer.instance.routes.get("/ps/workflows/{name:.+}")
async def get_workflow(request):
    file = os.path.abspath(
        os.path.join(workflows_directory, request.match_info["name"] + ".json")
    )
    if os.path.commonpath([file, workflows_directory]) != workflows_directory:
        return web.Response(status=403)
    return web.FileResponse(file)


@PromptServer.instance.routes.get("/ps/inputs/{filename}")
async def get_workflow(request):
    file = os.path.abspath(
        os.path.join(ps_inputs_directory, request.match_info["filename"])
    )
    if os.path.commonpath([file, ps_inputs_directory]) != ps_inputs_directory:
        return web.Response(status=403)
    return web.FileResponse(file)


@PromptServer.instance.routes.post("/ps/renders")
async def send_renders(request):
    try:
        data = await request.json()
        image_paths = data.get("images", [])
        
        encoded_images = []
        for path in image_paths[:4]:  # Maximum 4 cards
            with open(path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                encoded_images.append(encoded_string)
        
        await send_message(photoshop_users, "renders", json.dumps(encoded_images))
    except Exception as e:
        print(f"# PS: Error sending renders: {e}")
    return web.Response(text="Renders sent to ps")
