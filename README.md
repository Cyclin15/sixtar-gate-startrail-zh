# Sixtar Gate: STARTRAIL 简体中文汉化

《Sixtar Gate: STARTRAIL》(Steam, AppID 1802720) 的非官方简体中文汉化补丁。

适用于 Steam 版 build 25600030（Unity 2022.3.50f1，IL2CPP）。

## 下载安装

从 [Releases](../../releases) 下载最新版压缩包，然后：

1. 把压缩包内的 `SixtarGateSTARTRAIL-zh` 文件夹解压到游戏根目录（`Sixtar Gate STARTRAIL.exe` 所在目录）。
2. 双击文件夹内的 **安装.bat**。
3. 启动游戏，界面即为止体中文。

安装脚本会校验 `resources.assets.resS` 的文件大小，游戏版本不符时自动中止，不会损坏文件。

**卸载**：Steam 库中右键游戏 → 属性 → 已安装文件 → 验证游戏文件完整性，即可还原英文原版。

## 汉化内容

| 部分 | 说明 |
|------|------|
| 本地化文本表 | 系统 / 航行剧情 / 对话 / 解锁弹窗 4 张表全量汉化；操作提示表 43 条中 41 条汉化 |
| 场景硬编码文本 | 28 个场景资源文件中约 2300 处 TMP/Text 文本汉化 |
| 字体 | 烘焙 1831 个常用汉字的 SDF 字体图集，注入游戏字体兜底链，中文渲染无缺字 |

**有意保留原文的内容**：

- 曲名、曲师名
- 难度名（COMET / NOVA / QUASAR / SUPERNOVA / 코멧 / 퀘이사 等）
- SOLAR / LUNAR 模式名
- Enter / Cancel / SPACE / Key 等按键标签
- 操作提示表中 2 条文本（私人远航代码输入提示、"领取"按钮）——见下方已知问题

## 已知问题

- **InputGuide 表"撞车"问题**：当表中 `CustomizeGroup_SelectItemCategory` 与 `Setting_CategoryChange`
  两条被翻译成同一个中文词（"切换分类"）时，游戏内歌曲列表的曲绘（封面图）会全部消失；
  改成不同译词（"切换分类"/"更换分类"）即可恢复。全部 43 条翻译共存时仍会触发类似问题，
  机制未查明，因此最后 2 条保持英文。复现与二分定位过程见 `scripts/test_bisect.py` 的用法。
- 游戏更新后 `resources.assets.resS` 大小变化会导致安装中止，需等本补丁适配。

## 技术原理（构建管线）

游戏为 Unity 2022.3.50 IL2CPP + Addressables 构建，无官方中文。本仓库包含完整构建管线：

1. **`scripts/scan_ui.py`** — 扫描全部场景资源中 TMP/Text 组件的字符串及其在对象序列化数据中的偏移，
   产出 `data/ui_components.json`。
2. **`scripts/font_bake_v6.py`**（依赖 `scripts/font_patch.py`）— 用 FreeType 栅格化
   `data/charset_v6.txt` 中的 1831 个汉字，生成 4096×4096 Alpha8 SDF 图集（注意 Unity
   纹理首字节对应最底行，需逐字形垂直翻转），追加写入 `resources.assets.resS` 尾部，
   并修改游戏内 20+ 个 TMP 字体的 fallback 链指向它。
3. **`scripts/test_bisect.py`**（依赖 `scripts/localtbl.py`）— 重建本地化字符串表 bundle：
   解析原版 bundle（`backup/` 内）与 `data/zh_strings.json` 中的译文，按选定表/条目重组，
   用 LZ4HC 重新打包，计算 UnityFS bundle 的 CRC（对解压后数据块做 crc32）并回写
   `catalog.json` 中对应 Provider 条目的 `m_Crc` / `m_BundleSize`。
4. **`scripts/ui_patch.py`** — 按 `data/ui_components.json` 的偏移就地替换场景文件中的
   硬编码文本（校验 i32 长度前缀与原文 UTF-8 完全匹配后，从高偏移向低偏移替换，4 字节对齐填充）。
   译文表在 `data/zh_ui.py`（`TRANS` 翻译 / `SKIP` 保留原文）。
5. **`scripts/ui_revert_keys.py`** — 把按键类标签（Enter/Cancel/SPACE/Key）从中文还原回英文的就地逆替换。

> 注意：脚本中的路径为构建机的绝对路径（游戏目录 `D:\Steam\steamapps\common\Sixtar Gate STARTRAIL`），
> 在其他机器上复现时需自行调整。`backup/` 内含原版 `catalog.json` 与英文本地化 bundle 作为构建输入；
> 原版 `resources.assets` / `sharedassets*.assets` 需从自己的游戏安装中复制。

## 免责声明

本项目仅供学习交流，请通过 Steam 购买并支持正版游戏。
