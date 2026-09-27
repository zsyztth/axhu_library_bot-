"""PC端本地验证码求解 - 不依赖服务器"""
import cv2, base64, numpy as np
import ddddocr

class CaptchaSolver:
    def __init__(self):
        self.text_ocr = ddddocr.DdddOcr(beta=True, show_ad=False)
        self.det = ddddocr.DdddOcr(det=True, show_ad=False)
    
    def solve_text(self, img_path):
        """文字验证码"""
        with open(img_path, 'rb') as f:
            return self.text_ocr.classification(f.read())
    
    def solve_click(self, big_path, small_path):
        """点击验证码 - 模板匹配"""
        big = cv2.imread(big_path)
        small = cv2.imread(small_path)
        best = (0, None)
        for scale in [0.5,0.6,0.7,0.8,0.9,1.0,1.1,1.2,1.3,1.5,2.0]:
            w, h = int(small.shape[1]*scale), int(small.shape[0]*scale)
            if w > big.shape[1] or h > big.shape[0]: continue
            r = cv2.matchTemplate(big, cv2.resize(small,(w,h)), cv2.TM_CCOEFF_NORMED)
            _, s, _, p = cv2.minMaxLoc(r)
            if s > best[0]: best = (s, (p[0]+w//2, p[1]+h//2))
        return best[1], best[0]

if __name__ == '__main__':
    import sys
    solver = CaptchaSolver()
    if len(sys.argv) == 2:
        print("文字:", solver.solve_text(sys.argv[1]))
    elif len(sys.argv) == 3:
        x, y = solver.solve_click(sys.argv[1], sys.argv[2])
        print(f"坐标: ({x}, {y})")
