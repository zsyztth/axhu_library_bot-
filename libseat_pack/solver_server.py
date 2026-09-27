"""验证码解题服务 - 运行在服务器 43.142.49.114:8901"""
import cv2, base64, numpy as np
from flask import Flask, request, jsonify

app = Flask(__name__)

def match_template(big, small):
    """多尺度模板匹配，用于点击验证码"""
    best = (0, None)
    for scale in [0.5,0.6,0.7,0.8,0.9,1.0,1.1,1.2,1.3,1.5,1.8,2.0]:
        w, h = int(small.shape[1]*scale), int(small.shape[0]*scale)
        if w > big.shape[1] or h > big.shape[0]: continue
        r = cv2.matchTemplate(big, cv2.resize(small,(w,h)), cv2.TM_CCOEFF_NORMED)
        _, s, _, p = cv2.minMaxLoc(r)
        if s > best[0]: best = (s, (p[0]+w//2, p[1]+h//2))
    return best[1], best[0]

@app.route('/solve', methods=['POST'])
def solve():
    try:
        d = request.json
        big = cv2.imdecode(np.frombuffer(base64.b64decode(d['big']), np.uint8), 1)
        small = cv2.imdecode(np.frombuffer(base64.b64decode(d['small']), np.uint8), 1) if d.get('small') else None
        
        if small is not None and small.shape[0] > 0:
            pos, conf = match_template(big, small)
            return jsonify({"type":"click","x":pos[0],"y":pos[1],"conf":round(float(conf),4)})
        else:
            import ddddocr
            ocr = ddddocr.DdddOcr(beta=True, show_ad=False)
            _, buf = cv2.imencode('.png', big)
            text = ocr.classification(buf.tobytes())
            return jsonify({"type":"text","answer":text.strip()})
    except Exception as e:
        return jsonify({"error":str(e)}), 400

@app.route('/', methods=['GET'])
def health():
    return '{"status":"ok"}'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8901)
