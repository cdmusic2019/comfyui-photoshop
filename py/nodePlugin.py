from nodes import SaveImage
import hashlib
import asyncio
import json
import base64
import os
import time
import torch
import numpy as np
from PIL import Image, ImageOps
from io import BytesIO
import folder_paths
import torchvision.transforms.functional as tf
import aiohttp


nodepath = os.path.join(
    folder_paths.get_folder_paths("custom_nodes")[0], "comfyui-photoshop"
)

# New Refined Refactoring Node by Michoko92
def is_changed_file(filepath):
    """Return a deterministic cache key for a file (md5 hexdigest).

    ComfyUI's caching works best when IS_CHANGED returns a stable value.
    Returning the file hash itself avoids the "double run" behavior caused by NaN toggling.
    """
    try:
        with open(filepath, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception as e:
        print(f"Error in is_changed_file for {filepath}: {e}")
        return float("NaN")
class PhotoshopToComfyUI:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("IMAGE", "MASK", "FLOAT", "INT", "STRING", "STRING", "INT", "INT")
    RETURN_NAMES = ("Canvas", "Mask", "Slider", "Seed", "+", "-", "W", "H")
    FUNCTION = "PS_Execute"
    CATEGORY = "Photoshop"

    def PS_Execute(self):
        self.LoadDir()
        self.loadConfig()
        self.SendImg()

        sliderValue = self.slider / 100

        return (
            self.canvas,
            self.mask.unsqueeze(0),
            sliderValue,
            int(self.seed),
            self.psPrompt,
            self.ngPrompt,
            int(self.width),
            int(self.height),
        )

    def LoadDir(self, retry_count=0):
        try:
            self.canvasDir = os.path.join(
                nodepath, "data", "ps_inputs", "PS_canvas.png"
            )
            self.maskImgDir = os.path.join(nodepath, "data", "ps_inputs", "PS_mask.png")
            self.configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        except:
            time.sleep(1)
            if retry_count < 10:
                self.LoadDir(retry_count + 1)
            else:
                raise Exception(
                    "Failed to load directory after 5 attempts. \n 🔴 Make sure you have installed and started the Photoshop Plugin Successfully. \n 🔴 otherwise you can restart your Photoshop and your plugin to fix this problem."
                )

    def loadConfig(self, retry_count=0):
        try:
            with open(self.configJson, "r", encoding="utf-8") as file:
                self.ConfigData = json.load(file)
                self.imageCount = self.ConfigData.get("imageCount", 1)
        except:
            time.sleep(0.5)
            if retry_count < 4:
                self.loadConfig(retry_count + 1)
            else:
                raise Exception(
                    "Failed to load config after 5 attempts. \n 🔴 Make sure you have installed and started the Photoshop Plugin Successfully. \n 🔴 otherwise you can restart your Photoshop and your plugin to fix this problem."
                )

        self.psPrompt = self.ConfigData["positive"]
        self.ngPrompt = self.ConfigData["negative"]
        self.seed = self.ConfigData["seed"]
        self.slider = self.ConfigData["slider"]

    def SendImg(self):
        self.loadImg(self.canvasDir)
        self.canvas = self.i.convert("RGB")
        self.canvas = np.array(self.canvas).astype(np.float32) / 255.0
        self.canvas = torch.from_numpy(self.canvas)[None,]
        self.width, self.height = self.i.size

        self.loadImg(self.maskImgDir)
        self.i = ImageOps.exif_transpose(self.i)
        self.mask = np.array(self.i.getchannel("B")).astype(np.float32) / 255.0
        self.mask = torch.from_numpy(self.mask)

        # Convert #010101 to #000000
        self.mask = self.mask.numpy()  # Convert to numpy array for easier manipulation
        target_color = 1 / 255.0  # The float representation of #010101
        self.mask[self.mask == target_color] = 0.0  # Change target_color to 0.0
        self.mask = torch.from_numpy(self.mask)

    def loadImg(self, path):
        try:
            with open(path, "rb") as file:
                img_data = file.read()
            self.i = Image.open(BytesIO(img_data))
            self.i.verify()
            self.i = Image.open(BytesIO(img_data))
        except:
            self.i = Image.new(mode="RGB", size=(24, 24), color=(0, 0, 0))
        if not self.i:
            return

    @classmethod
    def IS_CHANGED(cls):
        try:
            configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
            canvasDir = os.path.join(nodepath, "data", "ps_inputs", "PS_canvas.png")
            maskImgDir = os.path.join(nodepath, "data", "ps_inputs", "PS_mask.png")

            config_changed = is_changed_file(configJson)
            canvas_changed = is_changed_file(canvasDir)
            mask_changed = is_changed_file(maskImgDir)

            return config_changed or canvas_changed or mask_changed
        except Exception as e:
            print("Error in IS_CHANGED:", e)
            return 0
# New Refined Refactoring Node  by Michoko92
class PhotoshopToComfyUI_new:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("IMAGE", "MASK", "INT", "INT")
    RETURN_NAMES = ("Canvas", "Mask", "W", "H")
    FUNCTION = "PS_Execute"
    CATEGORY = "Photoshop"

    def PS_Execute(self):
        self.LoadDir()
        self.loadConfig()
        self.SendImg()

        sliderValue = self.slider / 100

        return (
            self.canvas,
            self.mask.unsqueeze(0),
            int(self.width),
            int(self.height),
        )

    def LoadDir(self, retry_count=0):
        try:
            self.canvasDir = os.path.join(
                nodepath, "data", "ps_inputs", "PS_canvas.png"
            )
            self.maskImgDir = os.path.join(nodepath, "data", "ps_inputs", "PS_mask.png")
            self.configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        except:
            time.sleep(1)
            if retry_count < 10:
                self.LoadDir(retry_count + 1)
            else:
                raise Exception(
                    "Failed to load directory after 5 attempts. \n 🔴 Make sure you have installed and started the Photoshop Plugin Successfully. \n 🔴 otherwise you can restart your Photoshop and your plugin to fix this problem."
                )

    def loadConfig(self, retry_count=0):
        try:
            with open(self.configJson, "r", encoding="utf-8") as file:
                self.ConfigData = json.load(file)
                self.imageCount = self.ConfigData.get("imageCount", 1)
        except:
            time.sleep(0.5)
            if retry_count < 4:
                self.loadConfig(retry_count + 1)
            else:
                raise Exception(
                    "Failed to load config after 5 attempts. \n 🔴 Make sure you have installed and started the Photoshop Plugin Successfully. \n 🔴 otherwise you can restart your Photoshop and your plugin to fix this problem."
                )

        self.psPrompt = self.ConfigData["positive"]
        self.ngPrompt = self.ConfigData["negative"]
        self.seed = self.ConfigData["seed"]
        self.slider = self.ConfigData["slider"]

    def SendImg(self):
        self.loadImg(self.canvasDir)
        self.canvas = self.i.convert("RGB")
        self.canvas = np.array(self.canvas).astype(np.float32) / 255.0
        self.canvas = torch.from_numpy(self.canvas)[None,]
        self.width, self.height = self.i.size

        self.loadImg(self.maskImgDir)
        self.i = ImageOps.exif_transpose(self.i)
        self.mask = np.array(self.i.getchannel("B")).astype(np.float32) / 255.0
        self.mask = torch.from_numpy(self.mask)

        # Convert #010101 to #000000
        self.mask = self.mask.numpy()  # Convert to numpy array for easier manipulation
        target_color = 1 / 255.0  # The float representation of #010101
        self.mask[self.mask == target_color] = 0.0  # Change target_color to 0.0
        self.mask = torch.from_numpy(self.mask)

    def loadImg(self, path):
        try:
            with open(path, "rb") as file:
                img_data = file.read()
            self.i = Image.open(BytesIO(img_data))
            self.i.verify()
            self.i = Image.open(BytesIO(img_data))
        except:
            self.i = Image.new(mode="RGB", size=(24, 24), color=(0, 0, 0))
        if not self.i:
            return

    @classmethod
    def IS_CHANGED(cls):
        """Report changes when the Photoshop canvas or mask files change.

        Note: config.json changes are intentionally ignored here (handled by other nodes).
        """
        try:
            canvasDir = os.path.join(nodepath, "data", "ps_inputs", "PS_canvas.png")
            maskImgDir = os.path.join(nodepath, "data", "ps_inputs", "PS_mask.png")

            canvas_key = is_changed_file(canvasDir)
            mask_key = is_changed_file(maskImgDir)

            return f"{canvas_key}|{mask_key}"
        except Exception:
            return float("NaN")

# New Refined Refactoring Node  by Michoko92
class PhotoshopPromptsToComfyUI:
    """Prompt-only node for Photoshop plugin.

    Outputs (+) and (-) prompt strings from config.json.
    Designed so downstream nodes like CLIP Text Encode only re-run when the prompt text changes.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("+", "-")
    FUNCTION = "PS_Prompts"
    CATEGORY = "Photoshop"

    @staticmethod
    def _read_prompts_and_hash(config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pos = (data.get("positive", "") or "").strip()
        neg = (data.get("negative", "") or "").strip()

        h = hashlib.md5((pos + "\n---\n" + neg).encode("utf-8")).hexdigest()
        return pos, neg, h

    def PS_Prompts(self):
        configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        pos, neg, _ = self._read_prompts_and_hash(configJson)
        return (pos, neg)

    @classmethod
    def IS_CHANGED(cls):
        configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        try:
            _, _, h = cls._read_prompts_and_hash(configJson)
            # Return a deterministic key that changes only when prompts change
            return h
        except Exception:
            # If we can't read config, force downstream recompute
            return float("NaN")

# New Refined Refactoring Node  by Michoko92
class PhotoshopSliderToComfyUI:
    """Slider-only node for Photoshop plugin.

    Outputs the slider value (0.0–1.0) from config.json.
    Designed so downstream nodes only re-run when the slider value actually changes.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("Slider",)
    FUNCTION = "PS_Slider"
    CATEGORY = "Photoshop"

    @staticmethod
    def _read_slider_and_key(config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Plugin stores slider as 0..100; normalize to 0..1 for ComfyUI graph
        raw = data.get("slider", 0)
        try:
            raw_f = float(raw)
        except Exception:
            raw_f = 0.0

        slider = raw_f / 100.0
        # Deterministic cache key: use normalized value with fixed precision
        key = f"{slider:.6f}"
        return slider, key

    def PS_Slider(self):
        configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        slider, _ = self._read_slider_and_key(configJson)
        return (float(slider),)

    @classmethod
    def IS_CHANGED(cls):
        configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        try:
            _, key = cls._read_slider_and_key(configJson)
            return key
        except Exception:
            return float("NaN")

# New Refined Refactoring Node  by Michoko92
class PhotoshopSeedToComfyUI:
    """Seed-only node for Photoshop plugin.

    Outputs the seed value (INT) from config.json.
    Designed so downstream nodes only re-run when the seed value actually changes.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}}

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("Seed",)
    FUNCTION = "PS_Seed"
    CATEGORY = "Photoshop"

    @staticmethod
    def _read_seed_and_key(config_path: str):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw = data.get("seed", 0)
        try:
            seed = int(raw)
        except Exception:
            seed = 0

        # Deterministic cache key: exact integer
        key = str(seed)
        return seed, key

    def PS_Seed(self):
        configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        seed, _ = self._read_seed_and_key(configJson)
        return (int(seed),)

    @classmethod
    def IS_CHANGED(cls):
        configJson = os.path.join(nodepath, "data", "ps_inputs", "config.json")
        try:
            _, key = cls._read_seed_and_key(configJson)
            return key
        except Exception:
            return float("NaN")

class ComfyUIToPhotoshop(SaveImage):
    def __init__(self):
        self.output_dir = folder_paths.get_temp_directory()
        self.type = "temp"
        self.prefix_append = "_temp_"
        self.compress_level = 0

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "output": ("IMAGE",),
            },
            "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "execute"
    CATEGORY = "Photoshop"

    def tensor_to_bytes(self, tensor):
        """Convert image tensor to PNG binary data"""
        img_np = tensor.cpu().numpy()
        img_np = (img_np * 255).astype(np.uint8)
        pil_img = Image.fromarray(img_np)
        
        buffer = BytesIO()
        pil_img.save(buffer, format='PNG')
        buffer.seek(0)
        return buffer.getvalue()

    async def send_to_photoshop_binary(self, images_bytes_list):
        """Sending images to the backend via HTTP binary mode"""
        try:
            url = "http://127.0.0.1:8188/ps/render_binary"
            image_count = len(images_bytes_list)
            
            async with aiohttp.ClientSession() as session:
                for index, image_bytes in enumerate(images_bytes_list):
                    headers = {
                        'Content-Type': 'application/octet-stream',
                        'X-Image-Index': str(index),
                        'X-Image-Count': str(image_count),
                        'X-Filename': f'render_{index}.png'
                    }
                    print(f"# PS: Sending image {index+1}/{image_count} ({len(image_bytes)} bytes)...")
                    async with session.post(url, data=image_bytes, headers=headers) as response:
                        result = await response.json()
                        # print(f"# PS: Response: {result}")
                        if not result.get('success'):
                            print(f"# PS: Failed to send image {index+1}/{image_count}")
                            return None
            
            print(f"# PS: All {image_count} images sent successfully")
            return {"success": True, "count": image_count}
        except Exception as e:
            print(f"# PS: Error sending binary to Photoshop: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def execute(self, output, filename_prefix="PS_Output", prompt=None, extra_pnginfo=None):
        """Execute asynchronously - and return a preview"""
        
        # 1. First, use the parent class method to save the image (for node preview).
        results = self.save_images(output, filename_prefix, prompt, extra_pnginfo)
        
        # 2. Convert to binary data
        batch_size = min(output.shape[0], 9)  # Maximum 9 images
        images_bytes_list = []
        
        for i in range(batch_size):
            img_bytes = self.tensor_to_bytes(output[i])
            images_bytes_list.append(img_bytes)
            print(f"# PS: Converted image {i+1}/{batch_size} to binary ({len(img_bytes)} bytes)")
        
       
        await self.send_to_photoshop_binary(images_bytes_list)
        
       
        return results

class ClipPass:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"clip": ("CLIP",)}}

    RETURN_TYPES = ("CLIP",)
    RETURN_NAMES = ("clip",)
    FUNCTION = "exe"
    CATEGORY = "utils"

    def exe(self, clip):
        return (clip,)


class modelPass:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"model": ("MODEL",)}}

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "exe"
    CATEGORY = "utils"

    def exe(self, model):
        return (model,)


NODE_CLASS_MAPPINGS = {
    "🔹Photoshop ComfyUI Plugin": PhotoshopToComfyUI, 
    "🔹PhotoshopCanvasToComfyUI": PhotoshopToComfyUI_new,
    "🔹Photoshop Prompts": PhotoshopPromptsToComfyUI,
    "🔹Photoshop Slider": PhotoshopSliderToComfyUI,
    "🔹Photoshop Seed": PhotoshopSeedToComfyUI,
    "🔹SendTo Photoshop Plugin": ComfyUIToPhotoshop,
    "🔹ClipPass": ClipPass,
    "🔹modelPass": modelPass,
}

NODE_DISPLAY_NAME_MAPPINGS = {    
    "PhotoshopSeedToComfyUI": "🔹Photoshop Seed",
    "PhotoshopSliderToComfyUI": "🔹Photoshop Slider",
    "PhotoshopPromptsToComfyUI": "🔹Photoshop Prompts",
    "🔹Photoshop ComfyUI Plugin": "🔹Photoshop ComfyUI Plugin",
    "🔹PhotoshopCanvasToComfyUI": "🔹Photoshop Canvas",
    "SendToPhotoshop": "🔹Send To Photoshop",
    "ClipPass": "🔹ClipPass",
    "modelPass": "🔹modelPass",
}
