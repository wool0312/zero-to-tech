from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


from fastapi import FastAPI

app = FastAPI()

profile = {
    "heroTitle": "关于我",
    "heroSubtitle": "项目，创意，灵感，心得，我的作品",
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