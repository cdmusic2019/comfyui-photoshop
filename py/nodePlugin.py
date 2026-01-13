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


def is_changed_file(filepath):
    try:
        with open(filepath, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        if not hasattr(is_changed_file, "file_hashes"):
            is_changed_file.file_hashes = {}
        if filepath in is_changed_file.file_hashes:
            if is_changed_file.file_hashes[filepath] == file_hash:
                return False
        is_changed_file.file_hashes[filepath] = file_hash
        return float("NaN")
    except Exception as e:
        print(f"Error in is_changed_file for {filepath}: {e}")
        return False


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
    "🔹SendTo Photoshop Plugin": ComfyUIToPhotoshop,
    "🔹ClipPass": ClipPass,
    "🔹modelPass": modelPass,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PhotoshopToComfyUI": "🔹Photoshop ComfyUI Plugin",
    "SendToPhotoshop": "🔹Send To Photoshop",
    "ClipPass": "🔹ClipPass",
    "modelPass": "🔹modelPass",
}
