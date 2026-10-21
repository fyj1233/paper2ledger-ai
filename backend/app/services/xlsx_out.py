"""Excel 导出辅助。"""


def append_row(ws, row):
    """追加一行，并把被 openpyxl 自动识别成公式的单元格强制改回文本。

    单据中 OCR/大模型提取出的品名、客户、依据等字段可能以 = 开头，
    openpyxl 会把这类字符串写成真公式，导出的报表一打开就在阅读者机器上求值。
    """
    ws.append(list(row))
    for cell in ws[ws.max_row]:
        if cell.data_type == "f":
            cell.data_type = "s"
