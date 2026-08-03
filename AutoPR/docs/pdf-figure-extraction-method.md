# PDF 图表识别与裁剪方法

> 来源：导师提供的 mli-paper-reading skill（v1.2.0）Step 2 extract_figs.py
> 整理日期：2026-08-02

---

## 核心思路：两遍提取

### Pass 1：光栅图（内嵌位图）

```python
for pg_num in range(len(doc)):
    page = doc[pg_num]
    for img_info in page.get_images(full=True):
        xref = img_info[0]
        pix = fitz.Pixmap(doc, xref)
        if pix.width < 120 or pix.height < 120:  # 跳过装饰性小图
            continue
        if pix.n > 4:  # CMYK → RGB
            pix = fitz.Pixmap(fitz.csRGB, pix)
        # 导出 base64 PNG
```

- 信号源：`page.get_images(full=True)` 返回页内所有内嵌光栅图的 xref
- 过滤：宽或高 < 120px 视为装饰/噪点，跳过
- 输出：每张图的 Pixmap → PNG bytes → base64

### Pass 2：矢量/文本渲染图（整页裁剪）

对 Pass 1 未覆盖的页面：

```python
# 1. 判断该页是否有图
text = page.get_text()
if not any(kw in text.lower() for kw in ['figure ', 'fig.']):
    continue

# 2. 收集所有绘图路径 + 图块的 bbox
paths = page.get_drawings()
img_blocks = [b for b in page.get_text("dict")["blocks"] if b.get("type") == 1]
fig_rects = [fitz.Rect(p["rect"]) for p in paths if p["rect"][2]-p["rect"][0] > 20]
for ib in img_blocks:
    fig_rects.append(fitz.Rect(ib["bbox"]))

# 3. 合并为 union bbox + padding
union = fig_rects[0]
for r in fig_rects[1:]:
    union = union | r
clip = fitz.Rect(union.x0-10, union.y0-10, union.x1+10, union.y1+10)

# 4. 向下扩展到 caption 文字
for b in page.get_text("dict")["blocks"]:
    if b.get("type") != 0: continue
    bt = " ".join(s["text"] for ln in b["lines"] for s in ln["spans"])
    if "figure" in bt.lower() and fitz.Rect(b["bbox"]).y0 < clip.y1 + 60:
        clip = clip | fitz.Rect(b["bbox"])

# 5. 2× 渲染裁剪区
mat = fitz.Matrix(2.0, 2.0)
pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
```

- 信号源：`page.get_drawings()`（矢量路径）+ `get_text("dict")` type=1 块（图块）
- 裁剪：union bbox + 10pt padding，向下扩展 60pt 内的 caption
- 渲染：2× 矩阵保证清晰度
- 兜底：无 drawings 时取页面上方 65%

---

## 已知缺陷（对我们场景）

| # | 问题 | 影响 |
|---|------|------|
| 1 | caption 按下标匹配 `captions[img_idx]`，非位置匹配 | 多图页错配 |
| 2 | 整页 drawings 合并成一个 union bbox | 一页多图/多表糊成一坨 |
| 3 | Pass 2 跳过已有光栅图的页 | 同页混合位图+矢量图时漏掉矢量部分 |
| 4 | 无 Table 检测 | 表格完全丢失 |
| 5 | 无子图分组（Figure 1a/1b/1c） | 子图被合并或遗漏 |
| 6 | 无"数据图表 vs 流程图"分类 | 无法分流到不同处理 skill |
| 7 | 120px 阈值对碎片化瓦片（256×256）无效 | 论文图被拆成多块各自导出 |

---

## 我们的改进方向

### 架构

```
PDF 页面
  │
  ├─ ① 定位：找到所有 "Figure N:" / "Table N:" 文本行（锚点）
  │
  ├─ ② 归属：对每个锚点，向上收集属于它的图块/绘图路径/缩进文本行
  │     - 光栅碎片（256×256 瓦片）做空间聚类合并
  │     - 矢量路径按 bbox 邻近度归组
  │     - 纯文本渲染图用缩进行（x0 > 正文左边距）定界
  │
  ├─ ③ 裁剪：per-figure union bbox + padding → get_pixmap(clip=...)
  │
  ├─ ④ 识别：qwen3.8-max-preview 读取裁剪图，判断类型 + 提取信息
  │     ├─ 含数据图表（折线/柱状/表格）→ skill A：数据提取
  │     └─ 无数据流程图（架构/pipeline）→ skill B：流程重绘
  │
  └─ ⑤ 输出：裁剪 PNG + 结构化描述 + 分类标签
```

### 关键改进点

1. **caption 锚定分割**：先定位所有标注行，再按位置（而非下标）向上归属图块
2. **空间聚类**：对碎片化瓦片按 bbox 重叠/邻近度合并为完整图
3. **per-figure 裁剪**：每个 Figure/Table 独立 crop，不做整页 union
4. **混合页支持**：同一页既有位图又有矢量图时分别处理
5. **分类前置**：裁剪后立即交视觉模型分类，决定后续 skill 路由

### 依赖

- `pymupdf`（fitz）：PDF 解析、图块/绘图/文本提取、裁剪渲染
- `qwen3.8-max-preview`（百炼 API）：图像识别 + 分类 + 数据提取

---

## 参考：原 skill 完整提取脚本位置

`C:\Users\Administrator\Desktop\pdf识别图表格方法\SKILL.md` L193-261
