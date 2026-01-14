import fitz  # PyMuPDF
import cv2
import numpy as np
import os
from tkinter import filedialog, Tk, messagebox

# ===== 設定 =====
INPUT_DIR = "./input"
STAMP_DIR = "./stamp"
OUTPUT_DIR = "./output"
MAX_DISPLAY_SIZE = 900 

for d in [INPUT_DIR, STAMP_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

# 日本語パス対応のimread
def cv2_imread_unicode(path, flags=cv2.IMREAD_COLOR):
    try:
        n = np.fromfile(path, np.uint8)
        img = cv2.imdecode(n, flags)
        return img
    except Exception as e:
        print(f"読み込みエラー: {e}")
        return None

# 日本語パス対応のimwrite
def cv2_imwrite_unicode(path, img, ext=".jpg"):
    try:
        result, n = cv2.imencode(ext, img)
        if result:
            with open(path, mode='w+b') as f:
                n.tofile(f)
            return True
        else:
            return False
    except Exception as e:
        print(f"書き込みエラー: {e}")
        return False

def select_file(title, initialdir, filetypes):
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True) # ダイアログを最前面に
    file_path = filedialog.askopenfilename(initialdir=initialdir, title=title, filetypes=filetypes)
    root.destroy()
    return file_path

def ask_confirmation():
    root = Tk()
    root.withdraw()
    root.attributes('-topmost', True) # 確認画面を最前面に
    res = messagebox.askyesno("確定確認", "この位置とサイズで貼り付けます。よろしいですか？", parent=root)
    root.destroy()
    return res

def process_file(base_path, stamp_path):
    ext = os.path.splitext(base_path)[1].lower()
    
    # --- 1. ベース画像の準備 ---
    if ext == ".pdf":
        doc = fitz.open(base_path)
        page = doc[0]
        pdf_zoom = 1.5
        pix = page.get_pixmap(matrix=fitz.Matrix(pdf_zoom, pdf_zoom))
        bg_orig = cv2.cvtColor(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n), cv2.COLOR_RGB2BGR)
    else:
        bg_orig = cv2_imread_unicode(base_path)
        if bg_orig is None:
            print(f"エラー: ベース画像を読み込めませんでした。パスを確認してください: {base_path}")
            return
        doc = None

    # --- 2. スケーリング処理 ---
    h_orig, w_orig = bg_orig.shape[:2]
    display_ratio = 1.0
    if max(h_orig, w_orig) > MAX_DISPLAY_SIZE:
        display_ratio = MAX_DISPLAY_SIZE / max(h_orig, w_orig)
    
    bg_display = cv2.resize(bg_orig, (int(w_orig * display_ratio), int(h_orig * display_ratio)))

    p = {"x": 50, "y": 50, "w": 80, "h": 80, "mode": None, "confirmed": False}
    win_name = "Stamp Tool:     Enter=Confirm   /   Q=Quit"
    cv2.namedWindow(win_name)
    cv2.setWindowProperty(win_name, cv2.WND_PROP_TOPMOST, 1) # ウィンドウを最前面に

    def mouse_callback(event, x, y, flags, param):
        h_size = 12
        at_edge = (param["x"] + param["w"] - h_size < x < param["x"] + param["w"] + h_size and
                   param["y"] + param["h"] - h_size < y < param["y"] + param["h"] + h_size)
        if event == cv2.EVENT_LBUTTONDOWN:
            if at_edge: param["mode"] = "resize"
            elif param["x"] < x < param["x"] + param["w"] and param["y"] < y < param["y"] + param["h"]:
                param["mode"] = "move"
                param["offset_x"], param["offset_y"] = x - param["x"], y - param["y"]
        elif event == cv2.EVENT_MOUSEMOVE:
            if param["mode"] == "move":
                param["x"], param["y"] = x - param["offset_x"], y - param["offset_y"]
            elif param["mode"] == "resize":
                param["w"], param["h"] = max(10, x - param["x"]), max(10, y - param["y"])
        elif event == cv2.EVENT_LBUTTONUP: param["mode"] = None

    cv2.setMouseCallback(win_name, mouse_callback, p)

    # --- 3. 操作ループ ---
    while True:
        img_show = bg_display.copy()
        cv2.rectangle(img_show, (p["x"], p["y"]), (p["x"]+p["w"], p["y"]+p["h"]), (0, 0, 255), 2)
        cv2.rectangle(img_show, (p["x"]+p["w"]-5, p["y"]+p["h"]-5), (p["x"]+p["w"]+5, p["y"]+p["h"]+5), (0, 255, 0), -1)
        cv2.imshow(win_name, img_show)
        key = cv2.waitKey(1) & 0xFF
        if key == 13: # Enter
            if ask_confirmation():
                p["confirmed"] = True
                break
        elif key == ord('q'): break
    cv2.destroyAllWindows()

    # --- 4. 保存処理 ---
    if p["confirmed"]:
        output_filename = "output_" + os.path.basename(base_path)
        save_path = os.path.join(OUTPUT_DIR, output_filename)
        real_x, real_y = int(p["x"] / display_ratio), int(p["y"] / display_ratio)
        real_w, real_h = int(p["w"] / display_ratio), int(p["h"] / display_ratio)

        if doc:
            rect = fitz.Rect(real_x/pdf_zoom, real_y/pdf_zoom, (real_x+real_w)/pdf_zoom, (real_y+real_h)/pdf_zoom)
            page.insert_image(rect, filename=stamp_path)
            doc.save(save_path)
            doc.close()
        else:
            stamp_img = cv2_imread_unicode(stamp_path, cv2.IMREAD_UNCHANGED)
            if stamp_img is not None:
                stamp_resized = cv2.resize(stamp_img, (real_w, real_h), interpolation=cv2.INTER_LANCZOS4)
                y1, y2 = max(0, real_y), min(h_orig, real_y + real_h)
                x1, x2 = max(0, real_x), min(w_orig, real_x + real_w)
                stamp_crop = stamp_resized[0:y2-y1, 0:x2-x1]
                if stamp_crop.shape[2] == 4:
                    alpha = stamp_crop[:, :, 3] / 255.0
                    for c in range(3):
                        bg_orig[y1:y2, x1:x2, c] = (stamp_crop[:, :, c] * alpha + bg_orig[y1:y2, x1:x2, c] * (1.0 - alpha))
                else:
                    bg_orig[y1:y2, x1:x2] = stamp_crop[:, :, :3]
                
                cv2_imwrite_unicode(save_path, bg_orig, ext=os.path.splitext(save_path)[1])

        print(f"【完了】保存先: {save_path}")
        
        # --- 表示の修正 ---
        # 1. パス内のバックスラッシュをスラッシュに置換して読みやすくする
        # 2. フルパスに変換して、どこに保存されたかより明確にする
        clean_path = os.path.abspath(save_path).replace("\\", "/")
        
        root = Tk()
        root.overrideredirect(True)
        root.withdraw()
        root.attributes('-topmost', True)
        
        # 保存先を表示する前に少し余白（半角スペースや改行）を入れて見やすく調整
        messagebox.showinfo("完了", f"ファイル出力が完了しました！\n\n■保存先:\n   {clean_path}", parent=root)
        root.destroy()

if __name__ == "__main__":
    base_file = select_file("ベース選択", INPUT_DIR, [("All", "*.pdf;*.png;*.jpg;*.jpeg")])
    if base_file:
        stamp_file = select_file("スタンプ選択", STAMP_DIR, [("Images", "*.png;*.jpg;*.jpeg")])
        if stamp_file:
            process_file(base_file, stamp_file)