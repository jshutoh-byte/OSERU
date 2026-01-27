import fitz  # PyMuPDF
import cv2
import numpy as np
import os
import sys
from tkinter import filedialog, Tk, messagebox
from PIL import Image, ImageDraw, ImageFont

# ===== 設定・ディレクトリ構成 =====
INPUT_DIR = "./input"
STAMP_DIR = "./stamp"
OUTPUT_DIR = "./output"
MAX_DISPLAY_SIZE = 900  
FONT_PATH_TTF = "C:/Windows/Fonts/meiryo.ttc" # 日本語フォントパス

for d in [INPUT_DIR, STAMP_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

class StampApp:
    def __init__(self):
        # 座標管理。0も救済できるよう初期値を設定
        self.params = {
            "x": 50, "y": 50, "w": 80, "h": 80, 
            "mode": None, "confirmed": False,
            "offset_x": 0, "offset_y": 0
        }

    def put_japanese_text(self, img, text, pos, color=(255, 255, 255), size=18):
        """画像内に日本語の操作説明を書き込む(除霊用)"""
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(img_pil)
        font = ImageFont.truetype(FONT_PATH_TTF, size)
        draw.text(pos, text, font=font, fill=color)
        return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

    @staticmethod
    def cv2_imread_unicode(path, flags=cv2.IMREAD_COLOR):
        n = np.fromfile(path, np.uint8)
        return cv2.imdecode(n, flags)

    @staticmethod
    def cv2_imwrite_unicode(path, img, ext=".jpg"):
        result, n = cv2.imencode(ext, img)
        if result:
            with open(path, mode='w+b') as f:
                n.tofile(f)
            return True
        return False

    def select_file(self, title, initialdir, filetypes):
        root = Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(initialdir=initialdir, title=title, filetypes=filetypes)
        root.destroy()
        return file_path

    def process(self, base_path, stamp_path):
        ext = os.path.splitext(base_path)[1].lower()
        
        doc = None
        pdf_zoom = 2.0 
        if ext == ".pdf":
            doc = fitz.open(base_path)
            page = doc[0]
            mat = fitz.Matrix(pdf_zoom, pdf_zoom)
            pix = page.get_pixmap(matrix=mat)
            bg_orig = cv2.cvtColor(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n), cv2.COLOR_RGB2BGR)
        else:
            bg_orig = self.cv2_imread_unicode(base_path)

        # 表示用スケーリングとヘッダー追加
        h_orig, w_orig = bg_orig.shape[:2]
        display_ratio = MAX_DISPLAY_SIZE / max(h_orig, w_orig) if max(h_orig, w_orig) > MAX_DISPLAY_SIZE else 1.0
        bg_display_raw = cv2.resize(bg_orig, (int(w_orig * display_ratio), int(h_orig * display_ratio)))
        
        # 日本語ガイド用の黒い帯を追加(英語はもう出さない)
        header_h = 40
        bg_display = cv2.copyMakeBorder(bg_display_raw, header_h, 0, 0, 0, cv2.BORDER_CONSTANT, value=(30, 30, 30))
        guide_text = "【操作】 マウスで移動・右下で拡大縮小 | Enter：決定 | Q：やめる"
        bg_display = self.put_japanese_text(bg_display, guide_text, (10, 8))

        win_name = "OSERU - Den-shi Han-ko Tool"
        cv2.namedWindow(win_name)

        def mouse_callback(event, x, y, flags, param):
            h_size = 15 # 判定を少し広く
            # ヘッダー分を考慮した座標計算
            tx, ty = param["x"], param["y"] + header_h
            tw, th = param["w"], param["h"]
            
            at_edge = (tx + tw - h_size < x < tx + tw + h_size and
                       ty + th - h_size < y < ty + th + h_size)
            
            if event == cv2.EVENT_LBUTTONDOWN:
                if at_edge:
                    param["mode"] = "resize"
                elif tx < x < tx + tw and ty < y < ty + th:
                    param["mode"] = "move"
                    param["offset_x"], param["offset_y"] = x - tx, y - ty
            
            elif event == cv2.EVENT_MOUSEMOVE:
                if param["mode"] == "move":
                    param["x"], param["y"] = x - param["offset_x"], y - param["offset_y"] - header_h
                elif param["mode"] == "resize":
                    param["w"], param["h"] = max(10, x - tx), max(10, y - ty)
            
            elif event == cv2.EVENT_LBUTTONUP:
                param["mode"] = None

        cv2.setMouseCallback(win_name, mouse_callback, self.params)

        while True:
            img_show = bg_display.copy()
            p = self.params
            # 描画時にヘッダーの高さを加算
            dy = p["y"] + header_h
            cv2.rectangle(img_show, (p["x"], dy), (p["x"]+p["w"], dy+p["h"]), (0, 0, 255), 2)
            cv2.rectangle(img_show, (p["x"]+p["w"]-5, dy+p["h"]-5), (p["x"]+p["w"]+5, dy+p["h"]+5), (0, 255, 0), -1)
            cv2.imshow(win_name, img_show)
            
            key = cv2.waitKey(1) & 0xFF
            if key == 13: # Enter
                root = Tk(); root.withdraw(); root.attributes('-topmost', True)
                if messagebox.askyesno("確定", "この位置でハンコを押しますか？"):
                    self.params["confirmed"] = True
                    root.destroy(); break
                root.destroy()
            elif key == ord('q'): break
        
        cv2.destroyAllWindows()

        if self.params["confirmed"]:
            output_filename = "OSERU_" + os.path.basename(base_path)
            save_path = os.path.join(OUTPUT_DIR, output_filename)
            p = self.params
            
            real_x, real_y = int(p["x"] / display_ratio), int(p["y"] / display_ratio)
            real_w, real_h = int(p["w"] / display_ratio), int(p["h"] / display_ratio)

            if doc:
                pdf_w, pdf_h = page.rect.width, page.rect.height
                rx = pdf_w / (bg_orig.shape[1] / pdf_zoom)
                ry = pdf_h / (bg_orig.shape[0] / pdf_zoom)
                rect = fitz.Rect(real_x / pdf_zoom * rx, real_y / pdf_zoom * ry, 
                                 (real_x + real_w) / pdf_zoom * rx, (real_y + real_h) / pdf_zoom * ry)
                page.insert_image(rect, filename=stamp_path)
                doc.save(save_path); doc.close()
            else:
                stamp_img = self.cv2_imread_unicode(stamp_path, cv2.IMREAD_UNCHANGED)
                if stamp_img is not None:
                    stamp_resized = cv2.resize(stamp_img, (real_w, real_h), interpolation=cv2.INTER_LANCZOS4)
                    y1, y2 = max(0, real_y), min(h_orig, real_y + real_h)
                    x1, x2 = max(0, real_x), min(w_orig, real_x + real_w)
                    target_region = bg_orig[y1:y2, x1:x2]
                    stamp_region = stamp_resized[0:y2-y1, 0:x2-x1]

                    if stamp_region.shape[2] == 4:
                        alpha = stamp_region[:, :, 3] / 255.0
                        for c in range(3):
                            target_region[:, :, c] = (stamp_region[:, :, c] * alpha + target_region[:, :, c] * (1.0 - alpha))
                    else:
                        bg_orig[y1:y2, x1:x2] = stamp_region[:, :, :3]
                    self.cv2_imwrite_unicode(save_path, bg_orig, ext=os.path.splitext(save_path)[1])

            root = Tk(); root.withdraw(); root.attributes('-topmost', True)
            messagebox.showinfo("完了", f"保存しました！\n{save_path}")
            root.destroy()

if __name__ == "__main__":
    app = StampApp()
    b_file = app.select_file("1. 書類を選んでください", INPUT_DIR, [("PDF/画像", "*.pdf;*.png;*.jpg")])
    if b_file:
        s_file = app.select_file("2. ハンコ(画像)を選んでください", STAMP_DIR, [("画像", "*.png;*.jpg")])
        if s_file: app.process(b_file, s_file)