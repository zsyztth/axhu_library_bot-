"""
增强模板匹配器 — 利用收集的素材提高匹配精度
1. 将 wordImage 与素材库中所有小图比较，识别是哪个字
2. 用该字的裁剪样本在大图中多模板匹配
3. 多尺度和预处理 (灰度/二值化/边缘) 提升置信度
"""
import cv2, numpy as np, os, json

MATERIAL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "素材")

class AdvancedMatcher:
    def __init__(self):
        self.library = {}  # {char: [img, img, ...]}
        self._load_library()

    def _load_library(self):
        """加载素材库：每个字的所有裁剪样本"""
        if not os.path.exists(MATERIAL_DIR):
            print(f"[!] 素材目录不存在: {MATERIAL_DIR}")
            return
        for char in os.listdir(MATERIAL_DIR):
            char_dir = os.path.join(MATERIAL_DIR, char)
            if not os.path.isdir(char_dir):
                continue
            imgs = []
            for f in os.listdir(char_dir):
                if f.endswith("_ref.png"):
                    continue
                path = os.path.join(char_dir, f)
                img = cv2.imread(path)
                if img is not None:
                    imgs.append(img)
            if imgs:
                self.library[char] = imgs
        print(f"[+] 素材库加载: {len(self.library)} 个字, "
              f"总计 {sum(len(v) for v in self.library.values())} 个样本")

    def _preprocess(self, img, method="gray"):
        """预处理：灰度、二值化、边缘"""
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        if method == "gray":
            return gray
        elif method == "binary":
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return binary
        elif method == "edge":
            return cv2.Canny(gray, 50, 150)
        return gray

    def match_template_multi(self, big_img, template, scales=None, methods=None):
        """多尺度多方法模板匹配，返回最佳位置和置信度"""
        if scales is None:
            scales = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0]
        if methods is None:
            methods = [cv2.TM_CCOEFF_NORMED, cv2.TM_CCORR_NORMED]

        th, tw = template.shape[:2]
        best_score = 0
        best_pos = None

        for scale in scales:
            w, h = int(tw * scale), int(th * scale)
            if w > big_img.shape[1] or h > big_img.shape[0]:
                continue
            if w < 5 or h < 5:
                continue
            resized = cv2.resize(template, (w, h))

            for method in methods:
                result = cv2.matchTemplate(big_img, resized, method)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                if max_val > best_score:
                    best_score = max_val
                    best_pos = (max_loc[0] + w // 2, max_loc[1] + h // 2)

        return best_pos, best_score

    def find_in_big(self, big_img, word_img):
        """
        在 big_img 中找 word_img 的位置
        策略：1. 识别 word 是哪个字 → 2. 用该字所有样本匹配 → 3. 多预处理融合
        """
        # Step 1: 用 word_img 匹配素材库中的小图，识别是哪个字
        best_char = None
        best_char_score = 0
        word_gray = self._preprocess(word_img, "gray")

        for char, samples in self.library.items():
            for sample in samples:
                sample_gray = self._preprocess(sample, "gray")
                # 比较 word_img 和素材样本
                pos, score = self.match_template_multi(
                    word_gray, sample_gray,
                    scales=[0.5, 0.7, 1.0, 1.3, 1.5, 2.0],
                    methods=[cv2.TM_CCOEFF_NORMED]
                )
                if score > best_char_score:
                    best_char_score = score
                    best_char = char

        # Step 2: 用该字的素材样本匹配大图
        all_results = []
        big_gray = self._preprocess(big_img, "gray")
        big_binary = self._preprocess(big_img, "binary")

        # 直接用 word_img 匹配
        for method_name, big_version in [("gray", big_gray), ("binary", big_binary)]:
            pos, score = self.match_template_multi(big_version, word_gray)
            if pos:
                all_results.append((pos, score, "word_direct", method_name))

        # 如果识别出字，用样本匹配
        if best_char and best_char in self.library:
            for sample in self.library[best_char]:
                sample_gray = self._preprocess(sample, "gray")
                for method_name, big_version in [("gray", big_gray), ("binary", big_binary)]:
                    pos, score = self.match_template_multi(big_version, sample_gray)
                    if pos:
                        all_results.append((pos, score, f"sample_{best_char}", method_name))

        if not all_results:
            return None, 0

        # 返回最佳匹配
        all_results.sort(key=lambda x: -x[1])
        best = all_results[0]
        return best[0], best[1]  # (x, y), confidence

    def solve(self, big_img_bytes, word_img_bytes):
        """对外接口：接收图片字节，返回坐标"""
        big = cv2.imdecode(np.frombuffer(big_img_bytes, np.uint8), 1)
        word = cv2.imdecode(np.frombuffer(word_img_bytes, np.uint8), 1)
        if big is None or word is None:
            return None

        pos, conf = self.find_in_big(big, word)
        if pos:
            print(f"   [匹配] 位置=({pos[0]},{pos[1]}), 置信度={conf:.3f}")
            return pos[0], pos[1]
        return None


if __name__ == "__main__":
    import sys
    m = AdvancedMatcher()
    if len(sys.argv) >= 3:
        big = cv2.imread(sys.argv[1])
        small = cv2.imread(sys.argv[2])
        pos, conf = m.find_in_big(big, small)
        if pos:
            print(f"结果: ({pos[0]}, {pos[1]}), 置信度: {conf:.3f}")
