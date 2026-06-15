import os
import sqlite3
import secrets
import hashlib
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
import aiohttp
from dotenv import load_dotenv

load_dotenv()

LLM_API_URL = os.getenv("LLM_API_URL", "https://106aa2bd4e424e9297c5c9b554447432--8000.ap-shanghai2.cloudstudio.club/v1/completions")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "rewriter")
MIN_WORDS = int(os.getenv("MIN_WORDS", "10"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SAMPLE_N = int(os.getenv("SAMPLE_N", "8"))
LLM_PROMPT_TEMPLATE = os.getenv("LLM_PROMPT_TEMPLATE", (
    '<|begin_of_text|>User: #指令:请在【核心含义不变】且【严禁增减事实】的前提下，'
    '对待改写文本进行【深度句式重构】。\n'
    '#核心红线:\n'
    '1.【严禁拷贝】禁止原封不动搬运原句，必须通过大幅调整语序、变换句式来实现改写。\n'
    '2.【确定性对齐】必须严格保留原文的认识论层级，严禁将"可能"、"潜力"等词汇改为断定表述。\n'
    '3.【事实锁定】严禁引入原文未提及的任何数据、年份、示例或"脑补"细节。\n'
    '4.【引用锚定】必须原样保留文中所有的引注格式及内容，严禁遗漏或拼写错误；'
    '必须保留原文的逻辑连接词。\n'
    '#格式要求:只输出改写后的正文，保持单段落，严禁输出任何额外说明。\n'
    '###待改写文本:\n{input_text}\n\nAssistant:'
))

DB_PATH = Path("novelforge.db")
INITIAL_KEYS = [
    "RUNBIGE-2024-TEST-001",
    "RUNBIGE-2024-TEST-002",
    "RUNBIGE-2024-VIP-003",
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    # migrate old table if exists
    old_cols = [r[1] for r in conn.execute("PRAGMA table_info(rewrite_logs)").fetchall()]
    if "original_text" in old_cols:
        conn.executescript("DROP TABLE IF EXISTS rewrite_logs;")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS card_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            total_words INTEGER NOT NULL DEFAULT 100000,
            used_words INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS rewrite_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_key_id INTEGER NOT NULL,
            word_count INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (card_key_id) REFERENCES card_keys(id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_logs_card ON rewrite_logs(card_key_id);
    """)
    conn.commit()
    conn.close()


def init_card_keys():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) as cnt FROM card_keys").fetchone()
    if existing["cnt"] == 0:
        for key in INITIAL_KEYS:
            conn.execute("INSERT OR IGNORE INTO card_keys (key) VALUES (?)", (key,))
        conn.commit()
    conn.close()


def init_settings():
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) as cnt FROM settings").fetchone()
    if existing["cnt"] == 0:
        conn.executescript(f"""
            INSERT INTO settings (key, value) VALUES ('llm_api_url', '{LLM_API_URL}');
            INSERT INTO settings (key, value) VALUES ('llm_api_key', '{LLM_API_KEY}');
            INSERT INTO settings (key, value) VALUES ('llm_model', '{LLM_MODEL}');
        """)
        conn.commit()
    conn.close()


def get_settings_dict() -> dict:
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("static").mkdir(exist_ok=True)
    Path("templates").mkdir(exist_ok=True)
    init_db()
    init_card_keys()
    init_settings()
    yield


app = FastAPI(title="润笔阁", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def get_card_by_key(key: str):
    conn = get_db()
    card = conn.execute("SELECT * FROM card_keys WHERE key = ?", (key,)).fetchone()
    conn.close()
    return dict(card) if card else None


def check_session(request: Request):
    card_key = request.cookies.get("card_key")
    if not card_key:
        return None
    card = get_card_by_key(card_key)
    if not card or card["status"] != "active":
        return None
    if card["used_words"] >= card["total_words"]:
        return None
    return card


def deduct_words(card_id: int, words: int):
    conn = get_db()
    conn.execute("UPDATE card_keys SET used_words = used_words + ? WHERE id = ?", (words, card_id))
    conn.commit()
    conn.close()


def log_rewrite(card_id: int, words: int):
    conn = get_db()
    conn.execute(
        "INSERT INTO rewrite_logs (card_key_id, word_count) VALUES (?, ?)",
        (card_id, words),
    )
    conn.commit()
    conn.close()


def char_count(text: str) -> int:
    return len(text.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", ""))


async def call_llm(text: str, n: int) -> list[str]:
    s = get_settings_dict()
    api_url = s.get("llm_api_url", LLM_API_URL)
    api_key = s.get("llm_api_key", LLM_API_KEY)
    api_model = s.get("llm_model", LLM_MODEL)

    if not api_url:
        raise Exception("未配置 LLM 接口地址，请在管理后台设置")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    prompt = LLM_PROMPT_TEMPLATE.replace("{input_text}", text)

    payload = {
        "model": api_model,
        "prompt": [prompt],
        "stop": ["\n\n", "\nUser:"],
        "top_p": 1.0,
        "temperature": 0.4,
        "max_tokens": 2048,
        "stream": False,
        "n": n,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, headers=headers, json=payload, timeout=120) as resp:
            if resp.status != 200:
                error_body = await resp.text()
                raise Exception(f"API 错误 ({resp.status}): {error_body[:300]}")
            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise Exception("API 返回为空")
            return [c.get("text", "").strip() for c in choices]


@app.get("/")
async def root():
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if check_session(request):
        return RedirectResponse(url="/rewrite")
    return templates.TemplateResponse(request, "login.html", {"request": request})


@app.post("/login")
async def login(request: Request, card_key: str = Form(...)):
    card = get_card_by_key(card_key.strip())
    if not card:
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": "卡密无效"})
    if card["status"] != "active":
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": "卡密已失效"})
    if card["used_words"] >= card["total_words"]:
        return templates.TemplateResponse(request, "login.html", {"request": request, "error": "卡密额度已用完"})

    response = RedirectResponse(url="/rewrite", status_code=302)
    response.set_cookie(key="card_key", value=card_key.strip(), max_age=86400 * 7, httponly=True)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login")
    response.delete_cookie("card_key")
    return response


@app.get("/rewrite", response_class=HTMLResponse)
async def rewrite_page(request: Request):
    card = check_session(request)
    if not card:
        return RedirectResponse(url="/login")
    remaining = card["total_words"] - card["used_words"]
    return templates.TemplateResponse(request, "rewrite.html", {
        "card_key": card["key"][:20] + "***" if len(card["key"]) > 20 else card["key"],
        "remaining": remaining,
        "total_words": card["total_words"],
        "used_words": card["used_words"],
        "sample_n": SAMPLE_N,
    })


@app.post("/rewrite")
async def rewrite(request: Request, text: str = Form(...), n: int = Form(SAMPLE_N)):
    card = check_session(request)
    if not card:
        return JSONResponse({"error": "未登录或会话已过期"}, status_code=401)

    chars = char_count(text)
    if chars < MIN_WORDS:
        return JSONResponse({"error": f"文本太短，至少需要 {MIN_WORDS} 字"}, status_code=400)

    remaining = card["total_words"] - card["used_words"]
    if remaining < chars:
        return JSONResponse({"error": f"额度不足。剩余 {remaining} 字，需要 {chars} 字"}, status_code=400)

    try:
        rewritten = await call_llm(text, min(n, 8))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)

    deduct_words(card["id"], chars)
    new_remaining = card["total_words"] - card["used_words"] - chars
    log_rewrite(card["id"], chars)

    return JSONResponse({
        "original": text,
        "rewritten": rewritten,
        "char_count": chars,
        "remaining": new_remaining,
    })


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    admin_token = request.cookies.get("admin_token")
    expected_token = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
    if not admin_token or admin_token != expected_token:
        return templates.TemplateResponse(request, "admin.html", {"locked": True})

    conn = get_db()
    cards = conn.execute("SELECT * FROM card_keys ORDER BY created_at DESC").fetchall()
    logs = conn.execute("""
        SELECT r.id, r.word_count, r.created_at, c.key as card_key_name
        FROM rewrite_logs r
        JOIN card_keys c ON r.card_key_id = c.id
        ORDER BY r.created_at DESC
        LIMIT 100
    """).fetchall()
    conn.close()

    cards_list = [dict(c) for c in cards]
    logs_list = [dict(l) for l in logs]

    stats = {
        "total_cards": len(cards_list),
        "active_cards": sum(1 for c in cards_list if c["status"] == "active"),
        "total_used_words": sum(c["used_words"] for c in cards_list),
    }

    settings = get_settings_dict()
    return templates.TemplateResponse(request, "admin.html", {
        "locked": False,
        "cards": cards_list,
        "logs": logs_list,
        "stats": stats,
        "settings": settings,
    })


@app.post("/admin/login")
async def admin_login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin", status_code=302)
        token = hashlib.sha256(password.encode()).hexdigest()
        response.set_cookie(key="admin_token", value=token, max_age=86400, httponly=True)
        return response
    return templates.TemplateResponse(request, "admin.html", {
        "locked": True,
        "error": "密码错误",
    })


@app.post("/admin/generate")
async def generate_cards(request: Request, count: int = Form(5), words: int = Form(100000)):
    admin_token = request.cookies.get("admin_token")
    expected_token = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
    if not admin_token or admin_token != expected_token:
        return JSONResponse({"error": "未授权"}, status_code=401)

    conn = get_db()
    generated = []
    for _ in range(count):
        key = f"RUNBIGE-{secrets.token_hex(4).upper()}"
        conn.execute("INSERT INTO card_keys (key, total_words) VALUES (?, ?)", (key, words))
        generated.append(key)
    conn.commit()
    conn.close()

    return JSONResponse({"generated": generated})


def check_admin(request: Request) -> bool:
    admin_token = request.cookies.get("admin_token")
    expected_token = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
    return bool(admin_token and admin_token == expected_token)


@app.post("/admin/settings")
async def save_settings(
    request: Request,
    llm_api_url: str = Form(...),
    llm_api_key: str = Form(...),
    llm_model: str = Form(...),
):
    if not check_admin(request):
        return JSONResponse({"error": "未授权"}, status_code=401)

    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('llm_api_url', ?)", (llm_api_url,))
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('llm_api_key', ?)", (llm_api_key,))
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('llm_model', ?)", (llm_model,))
    conn.commit()
    conn.close()

    return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
