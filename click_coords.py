"""点击图片获取坐标 — 双击图片上的目标位置，终端输出坐标
用法: python click_coords.py [图片路径]
     不带参数则自动选择当前目录下的 captcha_image_*.jpg
"""
import sys, os, json, base64

def show_with_cv2(img_path):
    """OpenCV 方式：双击获取坐标"""
    import cv2
    img = cv2.imread(img_path)
    if img is None:
        print(f"无法打开图片: {img_path}")
        return

    print(f"图片尺寸: {img.shape[1]}x{img.shape[0]}")
    print("操作: 双击目标文字位置，按任意键关闭窗口")
    print()

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDBLCLK:
            coords = [{"x": x, "y": y}]
            encoded = base64.b64encode(json.dumps(coords).encode()).decode()
            print(f">>> 坐标: ({x}, {y})")
            print(f"    输入值: {x},{y}")
            print(f"    base64: {encoded}")
            # 画十字
            display = img.copy()
            cv2.line(display, (x-15, y), (x+15, y), (0, 0, 255), 2)
            cv2.line(display, (x, y-15), (x, y+15), (0, 0, 255), 2)
            cv2.imshow("click to get coords", display)

    cv2.imshow("click to get coords", img)
    cv2.setMouseCallback("click to get coords", on_mouse)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    if len(sys.argv) >= 2:
        img_path = sys.argv[1]
    else:
        files = [f for f in os.listdir(".") if f.startswith("captcha_image_") and f.endswith((".jpg",".png"))]
        if not files:
            files = [f for f in os.listdir(".") if f.startswith("captcha_word") and f.endswith((".jpg",".png"))]
        if not files:
            print("未找到图片，请指定路径: python click_coords.py <图片>")
            sys.exit(1)
        files.sort(key=lambda f: os.path.getsize(f), reverse=True)
        img_path = files[0]
        print(f"自动选择: {img_path}")

    if not os.path.exists(img_path):
        print(f"文件不存在: {img_path}")
        sys.exit(1)

    show_with_cv2(img_path)
