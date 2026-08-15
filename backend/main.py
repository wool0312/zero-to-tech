from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"], # 允许前端来源
    allow_methods=["GET", "POST"],  # 允许所有 HTTP 方法
    allow_headers=["*"],  # 允许所有请求头
)

profile = {
    "heroTitle": "关于我",
    "heroSubtitle": "项目，创意，灵感，心得，我的作品",
    "featuredWork": {
        "kicker": "作品",
        "title": "文字实验室",
        "copy": "拼音和情绪，挖掘中文里的细节",
        "linkLabel": "打开作品",
    },
    "identity": {
        "motto": "已识乾坤大，尤怜草木青",
        "learning": "零到全栈",
    },
}

class AnalyzeRequest(BaseModel):
    text: str

@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    return {
        "text": req.text,
        "score": 0.9,
        "label": "偏平静",
        "pinyin": "pian ping jing"
    }

@app.get("/api/profile")
def get_profile():
    return profile