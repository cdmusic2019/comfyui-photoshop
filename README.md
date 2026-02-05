<div align="center">
本版本是在V1.93的基础上优化和升级而来，它具有以下特点：
  1.  支持最新版的PS，优化了蒙版算法，支持PS2024-PS2026
  2.  获取高清PS文档。从PS中获取图片时支持获取高清PS元图片，清晰度和PS文档一致。
  3. 对rgthree最新版本支持。
  4. 图片数据支持二进制传送，本地实现秒传。大图片传送不再失败或等待时间太长。
  5. 多图支持，支持PS端接收 1-9张高清PNG图片。
  6. 节点粒度优化，节点细分，方便更专业的工作流定制 （by Michoko92）
  7. 云端支持，插件已支持云端使用，享受云端超大GPU绘图的乐趣。

特别说明：
    本人也是插件的使用者，长期使用本插件来做设计。但原仓库代码长期未维护，所以我将它做了优化，修复bug,和一些功能的升级，让插件变得更好用，我本来还打算再添加一些专业的功能，
    但近期我发现有人把这个优化的仓库打包售卖，或改一下前端面版换个名字销售，针对这种不耻行为，我经过考虑后，决定不再新增功能，当前的优化我将保留，大家可以放心使用。
   



# ✨ ComfyUI Photoshop Plugin    [![GitHub Stars](https://img.shields.io/github/stars/NimaNzrii/comfyui-photoshop?style=social)](https://github.com/NimaNzrii/comfyui-photoshop)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://studio.buymeacoffee.com/dashboard)
[![Discord](https://img.shields.io/badge/Join%20Discord-7289DA?style=for-the-badge&logo=discord&logoColor=white)](https://discord.com/invite/3eHAMWnx7Y)
[![Email](https://img.shields.io/badge/Email-nimanzriart%40gmail.com-D14836?style=for-the-badge&logo=gmail&logoColor=white)](mailto:nimanzriart@gmail.com)

Seamlessly integrate ComfyUI's powerful AI capabilities into your Photoshop workflow! 🚀

</div>

![Preview Image](https://raw.githubusercontent.com/NimaNzrii/comfyui-photoshop/main/data/PreviewFiles/pr1.jpg)


> [!NOTE]  
> <span style="color:blue">**Chinese (ZH & TW), Japanese, and Korean** languages have been added!</span>  
> _Simply click the Load SD1.5 button, and the workflow will automatically load in your ComfyUI language._  
> _Compatible with [AIGODLIKE-ComfyUI-Translation](https://github.com/AIGODLIKE/AIGODLIKE-ComfyUI-Translation) node._


## 🔥 What's New in v1.9

- Crop Over Selection with Padding
- Port Change Support
- Tiny Shortcuts for efficiency
- Preserve Selection feature
- Improved "Play on Channels" functionality
- Convenient In-Plugin Updates

<details>
<summary><b>📜 Full Patch Notes</b></summary>

| Version | Key Updates |
|---------|-------------|
| 1.9     | • Crop Over Selection<br>• Padding for Crop Selection<br>• Connect to ComfyUI Cloud<br>• Port Change Support<br>• Tiny Shortcuts<br>• Preserve Selection<br>• Smarter "Play on Channels"<br>• In-Plugin Updates |
| 1.8     | • Optimized UI<br>• Randomization Feature<br>• New Functional Buttons<br>• Resizable Text Fields<br>• Improved Panel Animations |
| 1.6 - 1.4 | • 2x Smoother Experience<br>• Real-Time Workflow Sync<br>• 3x Simpler Workflow<br>• Enhanced Image Saving<br>• Mask Preview<br>• Plugin Install Button<br>• 6x Faster Start-Up<br>• macOS Support<br>• Photopea Integration |
| 1.0     | Initial Release |

</details>

[![youtubelink](https://raw.githubusercontent.com/NimaNzrii/comfyui-photoshop/main/data/PreviewFiles/pr3.webp)](https://www.youtube.com/watch?v=i__ciRbs3VA&t=40s)

<details>
<summary><h1> 🛠️ Installation </h1> click to expand</summary>


> **Minimum:** 6GB Vram - 12GB RAM - Photoshop 2022 or newer

1. **Photoshop Plugin:**
   - Download and install using [This .CCX file](https://raw.githubusercontent.com/NimaNzrii/comfyui-photoshop/main/Install_Plugin/3e6d64e0_PS.ccx)
   - Set up with [ZXP UXP Installer](https://aescripts.com/learn/zxp-installer/)

2. **ComfyUI Workflow:**
   - Download [THIS Workflow](https://openart.ai/workflows/lreWarJbqiYPcDXnD8hh)
   - Drop it onto your ComfyUI
   - Install missing nodes via "ComfyUI Manager"

> 💡 **New to ComfyUI?** Follow our [step-by-step installation guide](https://www.youtube.com/watch?v=YD09xpQrNZ4&t=4s)!
</details>


<details>

<summary><h1> 📦 Required Files </h1> click to expand</summary>

1. **Checkpoints:** (Place in `ComfyUi/Models/Checkpoints/` folder)
   - Default: [EpicRealism Natural Sin RC1 VAE](https://civitai.com/api/download/models/143906?type=Model&format=SafeTensor&size=pruned&fp=fp16)
   - In-Painting: [EpicRealism pure Evolution V5-inpainting](https://civitai.com/api/download/models/134361?type=Model&format=SafeTensor&size=pruned&fp=fp16)

2. **Loras:** (Place in `ComfyUi/Models/Loras/` folder)
   - [Detailer Lora](https://civitai.com/api/download/models/62833?type=Model&format=SafeTensor)

3. **Install via ComfyUI manager > install Models > search:**
   - LCM LoRA SD1.5
   - ControlNet-v1-1 (lineart; fp16)
   - ControlNet-v1-1 (scribble; fp16)
   - ControlNet-v1-1 (inpaint; fp16)
   - 4x-UltraSharp

</details>

📜 This project is [licensed](https://github.com/NimaNzrii/comfyui-photoshop/blob/main/License).

<div align="center">

---

Made with ❤️ by [Nima Nazari](https://github.com/NimaNzrii)

[⭐ Star this repo](https://github.com/NimaNzrii/comfyui-photoshop) if you find it helpful!

</div>
