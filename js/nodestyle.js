import { connect, sendMsg } from "./connection.js";
import { loadWorkflow, nodever } from "./manager.js";
import { app as app } from "../../../scripts/app.js";
import { api as api } from "../../../scripts/api.js";

export let photoshopNode = [];
let setupdone = false;
let connectdone = false;
let disabledrow = false;
// onst canvasImage = await api.fetchApi(`/ps/inputs/PS_canvas.png`);
// const maskImage = await api.fetchApi(`/ps/inputs/PS_mask.png`);

//  旧模式（LiteGraph Canvas）：原有绘制逻辑，仅改名
function legacySetBackgroundImageContain(node, canvasUrl, maskUrl) {
  if (node.mode === 2) {
    return;
  }
  const fetchImage = (url) => {
    return new Promise((resolve, reject) => {
      const img = new Image();
      // Configure cross-domain attributes to prevent cloud-based cross-domain contamination of the canvas.
      img.crossOrigin = "Anonymous";
      img.src = url;
      img.onload = () => resolve(img);
      img.onerror = () => reject(`Failed to load image: ${url}`);
    });
  };
  Promise.all([fetchImage(canvasUrl), fetchImage(maskUrl)])
    .then(([canvasImg, maskImg]) => {
      const drawImage = () => {
        if (!disabledrow) {
          if (node.properties && node.properties["Disable Preview"]) {
            node.onDrawBackground = null;
            node.setDirtyCanvas(true, true);
            return;
          }
          const aspectRatio = canvasImg.width / canvasImg.height;
          const nodeAspectRatio = node.size[0] / node.size[1];
          let drawWidth, drawHeight, drawX, drawY;
          if (aspectRatio > nodeAspectRatio) {
            drawWidth = node.size[0];
            drawHeight = drawWidth / aspectRatio;
            drawX = 0;
            drawY = node.size[1] - drawHeight;
          } else {
            drawHeight = node.size[1];
            drawWidth = drawHeight * aspectRatio;
            drawX = (node.size[0] - drawWidth) / 2;
            drawY = 0;
          }
          node.onDrawBackground = function (ctx) {
            ctx.drawImage(canvasImg, drawX, drawY, drawWidth, drawHeight);
            ctx.globalAlpha = 0.7;
            ctx.globalCompositeOperation = "darken";
            ctx.drawImage(maskImg, drawX, drawY, drawWidth, drawHeight);
            ctx.globalCompositeOperation = "source-over";
          };
          node.setDirtyCanvas(true, true);
        }
      };
      drawImage();
      node.onResize = drawImage;
    })
    .catch((error) => {
      // console.error("🔹 Error:", error);
      node.onDrawBackground = null;
      node.setDirtyCanvas(true, true);
    });
}

//  Nodes 2.0（Vue 渲染）预览支持


const PS_PREVIEW_WIDGET = "ps_preview";
const PS_STYLE_ID = "ps-preview-style-v2";

// 检测是否启用 Nodes 2.0
const isVueNodesMode = () => {
  try {
    return !!app.extensionManager?.setting?.get?.("Comfy.VueNodes.Enabled");
  } catch {
    return false;
  }
};


function ensurePsStyle() {
  if (document.getElementById(PS_STYLE_ID)) return;
  const s = document.createElement("style");
  s.id = PS_STYLE_ID;
  s.textContent = `[data-ps-clear]{background-color:transparent !important;background-image:none !important;}`;
  document.head.appendChild(s);
}


const findNodeEl = (el) => el.closest?.("[data-node-id]") || null;


function findHeaderEl(nodeEl, layer) {
  const h = nodeEl.querySelector(".lg-node-header, [data-testid^='node-header']");
  if (h) return h;
  const first = nodeEl.firstElementChild;
  return first && first !== layer ? first : null;
}


const isOpaque = (bg) => bg && bg !== "transparent" && !/rgba\(.*,\s*0\)$/.test(bg);

function clearCovers(nodeEl, layer) {
  const rect = nodeEl.getBoundingClientRect();
  const area = rect.width * rect.height;
  const result = { bg: null, radius: null };
  if (!area) return result;

  
  const rootCs = getComputedStyle(nodeEl);
  if (isOpaque(rootCs.backgroundColor)) {
    result.bg = rootCs.backgroundColor;
    result.radius = rootCs.borderRadius;
  }

  for (const el of nodeEl.querySelectorAll("*")) {
    if (layer.contains(el)) continue;    
    if (el.hasAttribute("data-ps-clear")) {
      if (!result.bg && el.dataset.psBg) {
        result.bg = el.dataset.psBg;
        result.radius = el.dataset.psRadius;
      }
      continue;
    }
    const cs = getComputedStyle(el);
    if (!isOpaque(cs.backgroundColor) && cs.backgroundImage === "none") continue;
    const r = el.getBoundingClientRect();
    if (r.width * r.height < area * 0.3) continue;
    el.dataset.psBg = cs.backgroundColor;
    el.dataset.psRadius = cs.borderRadius;
    el.setAttribute("data-ps-clear", "");
    if (!result.bg && isOpaque(cs.backgroundColor)) {
      result.bg = cs.backgroundColor;
      result.radius = cs.borderRadius;
    }
  }
  return result;
}


function restoreCovers(nodeEl) {
  nodeEl?.querySelectorAll("[data-ps-clear]").forEach((el) => {
    el.removeAttribute("data-ps-clear");
    delete el.dataset.psBg;
    delete el.dataset.psRadius;
  });
}


function ensurePsPreviewWidget(node) {
  let w = node.widgets?.find((x) => x.name === PS_PREVIEW_WIDGET);
  if (w) return w;
  const spacer = document.createElement("div");
  spacer.style.cssText = "width:100%;height:0;pointer-events:none;";

  const layer = document.createElement("div");
  layer.style.cssText =
    "position:absolute;inset:0;z-index:-1;overflow:hidden;pointer-events:none;display:none;";

  
  const imgBox = document.createElement("div");
  imgBox.style.cssText = "position:absolute;left:0;right:0;top:0;bottom:0;overflow:hidden;";

  const imgCss = "position:absolute;inset:0;width:100%;height:100%;object-fit:contain;";
  const base = document.createElement("img");
  base.style.cssText = imgCss;
  base.alt = "Photoshop canvas preview";
  base.draggable = false;
  const mask = document.createElement("img");
  mask.style.cssText = imgCss + "opacity:0.7;mix-blend-mode:darken;";
  mask.alt = "";
  mask.setAttribute("aria-hidden", "true");
  mask.draggable = false;

  imgBox.append(base, mask);
  layer.appendChild(imgBox);

  let observedNodeEl = null;
  const layout = () => {
    const nodeEl = findNodeEl(spacer);
    if (!nodeEl) return; 
    if (layer.parentElement !== nodeEl) nodeEl.appendChild(layer);
    nodeEl.style.isolation = "isolate"; 
    if (getComputedStyle(nodeEl).position === "static") nodeEl.style.position = "relative";
    if (observedNodeEl !== nodeEl) {
      observedNodeEl = nodeEl;
      ro.observe(nodeEl);
    }

    
    if (layer.style.display === "none") {
      restoreCovers(nodeEl);
      return;
    }

    const header = findHeaderEl(nodeEl, layer);
    const headerH = header ? header.offsetHeight : 0;
    imgBox.style.top = `${headerH}px`;

    ensurePsStyle();
    const { bg, radius } = clearCovers(nodeEl, layer);
    layer.style.backgroundColor = bg || node.bgcolor || "#353535";
    layer.style.borderRadius = radius || getComputedStyle(nodeEl).borderRadius || "12px";
  };

  const ro = new ResizeObserver(() => requestAnimationFrame(layout));
  ro.observe(spacer);

  base.onload = () => {
    if (w._psHidden) return;
    layer.style.display = "block";
    layout();
  };
  base.onerror = () => {
    layer.style.display = "none";
    restoreCovers(findNodeEl(spacer));
  };
  mask.onload = () => {
    mask.style.display = "block";
  };
  mask.onerror = () => {
    mask.style.display = "none";
  };

  w = node.addDOMWidget(PS_PREVIEW_WIDGET, PS_PREVIEW_WIDGET, spacer, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => 0,
  });
  w.layerEl = layer;
  w.baseEl = base;
  w.maskEl = mask;
  w.layout = layout;
  w.spacerEl = spacer;
  w._psHidden = false;

  const origOnRemove = w.onRemove;
  w.onRemove = function () {
    ro.disconnect();
    restoreCovers(layer.parentElement);
    layer.remove();
    origOnRemove?.call(this);
  };
  return w;
}

// 切回旧模式时移除 2.0 的 DOM 控件
function removePsPreviewWidget(node) {
  const idx = node.widgets?.findIndex((x) => x.name === PS_PREVIEW_WIDGET) ?? -1;
  if (idx < 0) return;
  const w = node.widgets[idx];
  restoreCovers(w.layerEl?.parentElement);
  if (typeof node.removeWidget === "function") {
    node.removeWidget(w);
  } else {
    w.onRemove?.();
    node.widgets.splice(idx, 1);
  }
  w.layerEl?.remove();
}

function setBackgroundImageContain(node, canvasUrl, maskUrl) {
  if (!isVueNodesMode()) {
    removePsPreviewWidget(node);
    legacySetBackgroundImageContain(node, canvasUrl, maskUrl);
    return;
  }

  node.onDrawBackground = null;
  node.onResize = null;

  const w = ensurePsPreviewWidget(node);
  const hidden = node.mode === 2 || node.properties?.["Disable Preview"] || !canvasUrl;
  w._psHidden = !!hidden;
  if (hidden) {
    w.layerEl.style.display = "none";
    restoreCovers(findNodeEl(w.spacerEl));
    return;
  }

  w.baseEl.src = canvasUrl;
  if (maskUrl) {
    w.maskEl.src = maskUrl;
  } else {
    w.maskEl.style.display = "none";
  }
  w.layout();
}

let lastVueMode = isVueNodesMode();
setInterval(() => {
  const now = isVueNodesMode();
  if (now === lastVueMode) return;
  lastVueMode = now;
  photoshopNode.forEach((node) => {
    if (node.graph) previewonthenode(node);
  });
}, 1000);


// Dynamically build cloud-friendly URLs
async function previewonthenode(node) {
  const timestamp = new Date().getTime();
  const baseUrl = window.location.origin;

  let clientIdPrefix = "";
  try {
    // Call the new backend API, passing in the clientId of the current ComfyUI browser.
    // The backend will return the corresponding bound Photoshop client ID based on this ID or the request IP.
    const myClientId = api.clientId || "";
    const clientRes = await fetch(
      `${baseUrl}/ps/paired_client_id?clientId=${encodeURIComponent(myClientId)}`
    );

    if (clientRes.ok) {
      const data = await clientRes.json();
      if (data.ps_client_id && data.ps_client_id.trim() !== "") {
        clientIdPrefix = data.ps_client_id.trim() + "_";
      }
    }
  } catch (error) {
    console.warn("🔹 Could not fetch paired_client_id, falling back to default.", error);
  }
  // Dynamically concatenate image paths with the correct prefixes.
  const canvasImageUrl = `${baseUrl}/ps/inputs/${clientIdPrefix}PS_canvas.png?v=${timestamp}`;
  const maskImageUrl = `${baseUrl}/ps/inputs/${clientIdPrefix}PS_mask.png?v=${timestamp}`;

  setBackgroundImageContain(node, canvasImageUrl, maskImageUrl);
}

function drawUpdateTextAndRoundedStroke(ctx, node) {
  ctx.fillStyle = "blue";
  ctx.font = "bold 32px Arial";
  ctx.textAlign = "center";
  ctx.fillText("Update Available!", node.size[0] / 2, -45);
  const radius = 8;
  const offsetY = -28;
  ctx.strokeStyle = "blue";
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.moveTo(radius, offsetY);
  ctx.lineTo(node.size[0] - radius, offsetY);
  ctx.arcTo(node.size[0], offsetY, node.size[0], radius + offsetY, radius);
  ctx.lineTo(node.size[0], node.size[1] - radius);
  ctx.arcTo(node.size[0], node.size[1], node.size[0] - radius, node.size[1], radius);
  ctx.lineTo(radius, node.size[1]);
  ctx.arcTo(0, node.size[1], 0, node.size[1] - radius, radius);
  ctx.lineTo(0, radius + offsetY);
  ctx.arcTo(0, offsetY, radius, offsetY, radius);
  ctx.closePath();
  ctx.stroke();
}

function createWatchedObject(obj, onChange) {
  return new Proxy(obj, {
    set(target, property, value) {
      if (target[property] !== value) {
        target[property] = value;
        onChange(property, value);
      }
      return true;
    },
  });
}

async function addBooleanProperty(node) {
  if (!node.properties) {
    node.properties = {};
  }
  const properties = {
    "Disable Preview": false,
    "Dont Hide Buttons": false,
  };
  node.properties = createWatchedObject(properties, async (property, newValue) => {
    if (property === "Disable Preview") {
      // 统一走 previewonthenode，两种模式都适用
      previewonthenode(node);
    }
  });
}

function addRemoveButtons(node, add) {
  try {
    if (add) {
      addButton(node, "Load SD 1.5", "temp-button", () => loadWorkflow("sd15"));
      addButton(node, "Load sdxl (coming Soon...)", "temp-button", () => alert("We will drop it this week!"));
    } else {
      node.widgets = node.widgets.filter((widget) => widget.className !== "temp-button");
      node.setDirtyCanvas(true, true);
    }
  } catch (error) {
    console.error("🔹 Error in addRemoveButtons:", error);
  }
}

function handleMouseEvents(node) {
  const originalOnDrawForeground = node.onDrawForeground;
  node.onMouseEnter = () => {
    node.onDrawForeground = function (ctx) {
      if (originalOnDrawForeground) originalOnDrawForeground.call(this, ctx);
      ctx.fillStyle = "rgba(0, 0, 0, 0.4)";
      ctx.fillRect(0, 0, node.size[0], node.size[1]);
    };
    const tempButtonExists = node.widgets && node.widgets.some((widget) => widget.className === "temp-button");
    if (!tempButtonExists) {
      addRemoveButtons(node, true);
    }
    node.setDirtyCanvas(true, true);
  };
  node.onMouseLeave = () => {
    node.onDrawForeground = originalOnDrawForeground;
    if (!node.properties || !node.properties["Dont Hide Buttons"]) {
      addRemoveButtons(node, false);
    }
    node.setDirtyCanvas(true, true);
  };
}

// Define the setup function
function setup() {
  if (photoshopNode.length > 0 && !setupdone) {
    if (!connectdone) {
      connect();
      checkForNewVersion(nodever);
      connectdone = true;
    }
    setTimeout(() => {
      photoshopNode.forEach((node) => previewonthenode(node));
      setupdone = true;
    }, 6000);
  }
}

// Register extension with ComfyUI
app.registerExtension({
  name: "PhotoshopToComfyUINode2",
  setup: setup, // Reference the setup function here
  async nodeCreated(node) {
    try {
      if (node?.comfyClass === "🔹Photoshop ComfyUI Plugin" || node?.comfyClass === "🔹PhotoshopCanvasToComfyUI") {
        photoshopNode.push(node);
        addBooleanProperty(node);
        handleMouseEvents(node);
        if (node.properties && node.properties["Dont Hide Buttons"]) addRemoveButtons(node, true);
        setupdone = false;
        setup();
      }
    } catch (error) {
      console.error("🔹 Error in nodeCreated:", error);
    }
  },
});

api.addEventListener("execution_start", () => photoshopNode.forEach((node) => previewonthenode(node)));

let versionUrl = "https://raw.githubusercontent.com/NimaNzrii/comfyui-photoshop/main/data/PreviewFiles/version.json";

const checkForNewVersion = async (nodever) => {
  try {
    const response = await fetch(versionUrl);
    if (!response.ok) {
      throw new Error("Failed to fetch version information");
    }
    const data = await response.json();
    const latestVersion = data.version;
    console.log("🔹 latestVersion: ", latestVersion);
    const forceUpdate = data.force_update;
    if (latestVersion > nodever) {
      console.log(`🔹 New version available: ${latestVersion}`);
      if (forceUpdate) {
        photoshopNode.forEach((node) => {
          const existingButton = node.widgets?.find((widget) => widget.className === "update-ps-plugin-button");
          if (!existingButton) {
            const originalSize = [...node.size];
            addButton(node, "Click Here To Update🔥", "update-button", () => sendMsg("pullupdate", true));
            node.size = originalSize;
            const originalDrawForeground = node.onDrawForeground;
            node.onDrawForeground = function (ctx) {
              if (originalDrawForeground) originalDrawForeground.call(this, ctx);
              drawUpdateTextAndRoundedStroke(ctx, this);
            };
          }
        });
      } else {
        console.log("You are using the latest version.");
      }
    }
  } catch (error) {
    console.error("🔹 Error checking for new version:", error);
  }
};

function addButton(node, btntxt, class__name, func) {
  try {
    disabledrow = true;
    const originalSize = [...node.size];
    const button = node.addWidget("button", btntxt, null, func);
    button.className = class__name;
    const afterbtnHeight = node.size[1];
    if (originalSize[1] < afterbtnHeight) node.size = [originalSize[0], afterbtnHeight];
    else node.size = originalSize;
    node.setDirtyCanvas(true, true);
    disabledrow = false;
    // 2.0 模式下 onResize 会被置空，需要可选调用
    node.onResize?.();
  } catch (error) {
    console.error("🔹 Error in addButton:", error);
  }
}
