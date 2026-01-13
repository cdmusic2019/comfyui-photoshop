//The node now supports the latest version of :rgthree, version 1.0.2512112053, and the nightly build from the same day.
import { app as app } from "../../../scripts/app.js";
import { api as api } from "../../../scripts/api.js";
import { sendMsg, addListener } from "./connection.js";
import { photoshopNode } from "./nodestyle.js";

export const nodever = "1.9.3";
let workflowSwitcher = "";
let rndrModeSwitcher = "";
let workflowInterval = null;
let rndrInterval = null;


function getSafeColor(node) {
    if (!node) return "";
    


    if (node.properties) {
        if (node.properties["Color"]) return node.properties["Color"].toLowerCase();
        if (node.properties["color"]) return node.properties["color"].toLowerCase();
    }

    // 2. Attempt to obtain LiteGraph standard rendering colors
    return (node.color || node.bgcolor || "").toLowerCase();
}

function identifyNode(node) {
 
    if (node.comfyClass !== "Fast Groups Muter (rgthree)") return;

    const nodeTitle = (node.title || "").trim();
    //const c = getSafeColor(node); 
    const c = getSafeColor(node) || "#000"; 
   

    // Settings color
  
    const isGreen =       
        c === "#223322" || c === "#232" || //green
        c === "#4e5e4e" || // Compatible with older versions
        c === "#332222" || c === "#322" || 
        c === "#332922"; 
        

    // Workflow color
    const isBlue =          
        c === "#222233" || c === "#223" || //blue
        c === "#2a363b" ||  // palu blue
        c === "#2b4557" || //Compatible with older versions
        c === "#223333" || c === "#233" || //cyan
        c === "#332233" || c === "#323" || //prurle  
        c === "#443322" || c === "#432" || //yellow
        c === "#000" ||  //
        c === "#222222" || c === "#222"//BLACK


   
    if (!workflowSwitcher) {
        if (nodeTitle.startsWith("📁") || isBlue) {
            workflowSwitcher = node;
            console.log(`🔹 [PS Plugin] Workflow Switcher Found! ID: ${node.id}, Color detected: ${c}`);
            startWorkflowChecker();
        }
    }

    
    if (!rndrModeSwitcher) {
        if (nodeTitle.startsWith("⚙️") || isGreen) {
            rndrModeSwitcher = node;
            console.log(`🔹 [PS Plugin] Render Mode Switcher Found! ID: ${node.id}, Color detected: ${c}`);
            startRenderChecker();
        }
    }
}

function scanForSwitchers() {
    if (!app.graph) return;
    const nodes = app.graph._nodes;
    if (nodes && nodes.length > 0) {
        nodes.forEach(node => {
            identifyNode(node);
        });
    }
}

// --- Core repair function ---
function handleSwitcherClick(targetIndex, switcherNode) {
    try {
        const targetIdx = parseInt(targetIndex);
        if (!switcherNode || !switcherNode.widgets) {
            console.error("🔹 Switcher node not found.");
            return;
        }

        const widgets = switcherNode.widgets;                  
            widgets.forEach((widget, index) => {         
            const shouldBeOn = (index === targetIdx);
            const isRgthreeWidget = (widget.type === "RGTHREE_TOGGLE_AND_NAV") || (widget.value && typeof widget.value === 'object' && 'toggled' in widget.value);
            let valueChanged = false;

            // 1. Modify the data layer
            if (isRgthreeWidget) {
                // If the current state does not match the target state, make modifications.
                if (widget.value.toggled !== shouldBeOn) {
                    widget.value.toggled = shouldBeOn;
                    valueChanged = true;
                }
            } else {
                   if (widget.value !== shouldBeOn) {
                    widget.value = shouldBeOn;
                    valueChanged = true;
                }
            }

            // 2.If the target is activated, or if any state changes occur, the node needs to be notified.
            if (valueChanged || shouldBeOn) {
                
              
                if (isRgthreeWidget && widget.doModeChange) {
                    // doModeChange(forceState, skipOtherCheck)
                   
                    widget.doModeChange(shouldBeOn, true);
                }
                                
                if (widget.callback) {
                    try {
                         
                         widget.callback(widget.value, app.canvas, switcherNode, {x:0, y:0}, {});
                    } catch(e) { /* Ignore errors */ }
                }

               
                if (switcherNode.onWidgetChanged) {
                    switcherNode.onWidgetChanged(widget.name, widget.value, null, widget);
                }
            }
        });

        // 3. Force refresh the chart (Re-compute)
        
        switcherNode.setDirtyCanvas(true, true);
        app.graph.setDirtyCanvas(true, true);
        
        
        if (switcherNode.onResize) switcherNode.onResize(switcherNode.size);

    } catch (error) {
        console.error("🔹 Error in handleSwitcherClick:", error);
    }
}

addListener("photoshopConnected", () => {
  console.log("🔹photoshopConnected");
  try {
    if (workflowSwitcher) sendMsg("Send_workflow", SwitcherWidgetNames(workflowSwitcher));
    if (rndrModeSwitcher) sendMsg("Send_rndrMode", SwitcherWidgetNames(rndrModeSwitcher));
  } catch (error) {
    console.error("🔹 Error in photoshopConnected listener:", error);
  }
});

addListener("workflow", (data) => {
  try {
    console.log("🔹 Received workflow selection index:", data);
    handleSwitcherClick(data, workflowSwitcher);
  } catch (error) {
    console.error("🔹 Error in workflow listener:", error);
  }
});

addListener("alert", (data) => {
  try {
    alert(data);
  } catch (error) {
    console.error("🔹 Error in alert listener:", error);
  }
});

addListener("queue", (data) => {
  try {
    if (!isProcessing) {
      if (photoshopNode.length > 0) {
        isProcessing = true;
        (function processQueue() {
          if (genrateStatus == "genrated") {
            app.queuePrompt();
            isProcessing = false;
          } else {
            setTimeout(processQueue, 100);
          }
        })();
      } else {
        console.log("🔹 Photoshop Node doesn't Exist");
      }
    }
  } catch (error) {
    console.error("🔹 Error in queue listener:", error);
  }
});

addListener("rndrMode", (data) => {
  try {
    console.log("🔹 Received rndrMode selection index:", data);
    handleSwitcherClick(data, rndrModeSwitcher);
  } catch (error) {
    console.error("🔹 Error in rndrMode listener:", error);
  }
});

const SwitcherWidgetNames = (switcher) => {
  try {
    let widgetNames = [];
    let widgets = switcher.widgets;
    
    if (!widgets) return widgetNames;

    widgets.forEach((widget) => {
      let isEnabled = false;
      let displayName = "";

      // fast_groups_muter_1.025
      if (widget.type === "RGTHREE_TOGGLE_AND_NAV" || (widget.value && typeof widget.value === 'object' && 'toggled' in widget.value)) {
        isEnabled = widget.value.toggled;
        displayName = widget.label || widget.name || "Unknown"; 
      } else {
        isEnabled = !!widget.value;
        displayName = widget.name || "";
      }

      displayName = String(displayName.replace("Enable ", ""));

      if (isEnabled) {
        widgetNames.push({ name: displayName, selected: true });
      } else {
        widgetNames.push({ name: displayName });
      }
    });
    return widgetNames;
  } catch (error) {
    console.error("🔹 Error in SwitcherWidgetNames:", error);
    return [];
  }
};


function startWorkflowChecker() {
  if (workflowInterval) clearInterval(workflowInterval); // Clear existing to avoid duplicates
  if (!workflowSwitcher) return;
  
  const getWidgetStates = (node) => {
    return JSON.stringify(node?.widgets?.map(w => ({
      name: w.name, 
      label: w.label, 
      value: (w.value && typeof w.value === 'object' && 'toggled' in w.value) ? w.value.toggled : w.value
    })));
  };
  let previousWorkflowWidgets = getWidgetStates(workflowSwitcher);
  
  workflowInterval = setInterval(() => {
    try {
      if(!workflowSwitcher) { clearInterval(workflowInterval); return; } // Safety check
      const currentWorkflowWidgets = getWidgetStates(workflowSwitcher);
      if (currentWorkflowWidgets !== previousWorkflowWidgets) {
        console.log("Workflow switcher widgets have changed");
        sendMsg("Send_workflow", SwitcherWidgetNames(workflowSwitcher));
        previousWorkflowWidgets = currentWorkflowWidgets;
      }
    } catch (error) {
      console.error("🔹 Error in workflow checker:", error);
    }
  }, 3000);
}

function startRenderChecker() {
  if (rndrInterval) clearInterval(rndrInterval);
  if (!rndrModeSwitcher) return;

  const getWidgetStates = (node) => {
    return JSON.stringify(node?.widgets?.map(w => ({
      name: w.name, 
      label: w.label, 
      value: (w.value && typeof w.value === 'object' && 'toggled' in w.value) ? w.value.toggled : w.value
    })));
  };
  let previousRndrModeWidgets = getWidgetStates(rndrModeSwitcher);
  
  rndrInterval = setInterval(() => {
    try {
      if(!rndrModeSwitcher) { clearInterval(rndrInterval); return; }
      const currentRndrModeWidgets = getWidgetStates(rndrModeSwitcher);
      if (currentRndrModeWidgets !== previousRndrModeWidgets) {
        console.log("Render mode switcher widgets have changed");
        sendMsg("Send_rndrMode", SwitcherWidgetNames(rndrModeSwitcher));
        previousRndrModeWidgets = currentRndrModeWidgets;
      }
    } catch (error) {
      console.error("🔹 Error in render mode checker:", error);
    }
  }, 3000);
}





// Register extension with ComfyUI
app.registerExtension({
  name: "PhotoshopToComfyUINode",
  
  // 1. Perform a scan during initialization
  async setup() {
     
     setTimeout(() => {
        scanForSwitchers();
     }, 1000);
     setTimeout(() => {
        scanForSwitchers(); // try
     }, 3000);
  },

  async beforeRegisterNodeDef(nodeType, nodeInfo, appInstance) {
    if (nodeInfo.category === "Photoshop") {
      appendMenuOption(nodeType, (_, menuOptions) => {
        menuOptions.unshift({
          content: "🔹 Install PS Plugin V" + nodever,
          callback: () => sendMsg("install_plugin"),
        });
      });
    }
  },

  onProgressUpdate(event) {
     // ... (Your original code)
     try {
      if (!this.connected) return;
      let prompt = event.detail.prompt;
      if (prompt?.errorDetails) {
        // ...
      }
    } catch (error) {}
  },


  async nodeCreated(node) {
    try {
      
        setTimeout(() => {
            identifyNode(node);
        }, 100);
    } catch (error) {
      console.error("🔹 Error in nodeCreated:", error);
    }
  },
  
 
  async loadedGraphNode(node) {
   
      identifyNode(node);
  }
});

async function getWorkflow(name) {
  try {
    console.log("name: ", name);
    const response = await api.fetchApi(`/ps/workflows/${encodeURIComponent(name)}`, { cache: "no-store" });
    console.log("response: ", response);
    return await response.json();
  } catch (error) {
    console.error("🔹 Error in getWorkflow:", error);
  }
}

export async function loadWorkflow(workflowName) {
  const supportedLocales = ["ja-JP", "ko-KR", "zh-TW", "zh-CN"];
  let currentLocale = localStorage.getItem("AGL.Locale");
  if (!supportedLocales.includes(currentLocale)) {
    currentLocale = "en-US";
  }
  console.log("🔹 Load workflow for this language:", currentLocale);
  workflowName = workflowName + "_" + currentLocale;
  try {
    const workflowData = await getWorkflow(workflowName);
    app.loadGraphData(workflowData);
  } catch (error) {
    console.error(`Failed to load workflow ${workflowName}:`, error);
    alert(`Failed to load workflow ${workflowName}`);
  }
}

let genrateStatus = "genrated";
let isProcessing = false;

api.addEventListener("execution_start", ({ detail }) => {
  try {
    genrateStatus = "genrating";
    sendMsg("render_status", "genrating");
  } catch (error) {
    console.error("🔹 Error in execution_start listener:", error);
  }
});

api.addEventListener("executing", ({ detail }) => {
  try {
    if (!detail) {
      genrateStatus = "genrated";
      isProcessing = false;
      sendMsg("render_status", "genrated");
    }
  } catch (error) {
    console.error("🔹 Error in executing listener:", error);
  }
});

api.addEventListener("execution_error", ({ detail }) => {
  try {
    genrateStatus = "genrate_error";
    sendMsg("render_status", "genrate_error");
  } catch (error) {
    console.error("🔹 Error in execution_error listener:", error);
  }
});

api.addEventListener("progress", ({ detail: { value, max } }) => {
  try {
    let progress = Math.floor((value / max) * 100);
    if (!isNaN(progress) && progress >= 0 && progress <= 100) {
      sendMsg("progress", progress);
    }
  } catch (error) {
    console.error("🔹 Error in progress listener:", error);
  }
});

export function appendMenuOption(nodeType, callbackFn) {
  const originalMenuOptions = nodeType.prototype.getExtraMenuOptions;
  nodeType.prototype.getExtraMenuOptions = function () {
    const options = originalMenuOptions ? originalMenuOptions.apply(this, arguments) : [];
    callbackFn.apply(this, arguments);
    return options;
  };
}

function workflowswitcherchecker() {
  if (!workflowSwitcher) return;
  
  const getWidgetStates = (node) => {
    return JSON.stringify(node?.widgets?.map(w => ({
      name: w.name, 
      label: w.label, 
      value: (w.value && typeof w.value === 'object' && 'toggled' in w.value) ? w.value.toggled : w.value
    })));
  };

  let previousWorkflowWidgets = getWidgetStates(workflowSwitcher);
  
  setInterval(() => {
    try {
      const currentWorkflowWidgets = getWidgetStates(workflowSwitcher);
      if (currentWorkflowWidgets !== previousWorkflowWidgets) {
        console.log("Workflow switcher widgets have changed");
        sendMsg("Send_workflow", SwitcherWidgetNames(workflowSwitcher));
        previousWorkflowWidgets = currentWorkflowWidgets;
      }
    } catch (error) {
      console.error("🔹 Error in workflow switcher widget change detection:", error);
    }
  }, 3000);
}

function rndrswitcherchecker() {
  if (!rndrModeSwitcher) return;

  const getWidgetStates = (node) => {
    return JSON.stringify(node?.widgets?.map(w => ({
      name: w.name, 
      label: w.label, 
      value: (w.value && typeof w.value === 'object' && 'toggled' in w.value) ? w.value.toggled : w.value
    })));
  };

  let previousRndrModeWidgets = getWidgetStates(rndrModeSwitcher);
  
  setInterval(() => {
    try {
      const currentRndrModeWidgets = getWidgetStates(rndrModeSwitcher);
      if (currentRndrModeWidgets !== previousRndrModeWidgets) {
        console.log("Render mode switcher widgets have changed");
        sendMsg("Send_rndrMode", SwitcherWidgetNames(rndrModeSwitcher));
        previousRndrModeWidgets = currentRndrModeWidgets;
      }
    } catch (error) {
      console.error("🔹 Error in render mode switcher widget change detection:", error);
    }
  }, 3000);
}
