from fastapi import FastAPI, Form, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import mysql.connector
from fastapi.responses import JSONResponse

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="some-random-string")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/signup")
async def signup(request: Request, name: str = Form(...), username: str = Form(...), password: str = Form(...)):
    conn = mysql.connector.connect(
        host="localhost",
        user="websiteuser",
        password="websitepassword",
        database="website"
    )
    cursor = conn.cursor()

    # 檢查用戶名是否已存在
    cursor.execute("SELECT name FROM member WHERE username = %s", (username,))
    member = cursor.fetchone()
    if member:
        cursor.close()
        conn.close()
        message = "Repeated username"
        return RedirectResponse(url=f"/error?message={message}", status_code=status.HTTP_303_SEE_OTHER)
    
    # 用戶名不存在，新增用戶到資料庫
    cursor.execute("INSERT INTO member (name, username, password) VALUES (%s, %s, %s)", (name, username, password))
    conn.commit()  # 確認插入操作
    cursor.close()
    conn.close()
    return RedirectResponse(url="/?message=註冊成功", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/signin")
async def signin(request: Request, username: str = Form(...), password: str = Form(...)):
    # 建立資料庫連接
    conn = mysql.connector.connect(
        host="localhost",
        user="websiteuser",
        password="websitepassword",
        database="website"
    )
    cursor = conn.cursor()

    # 從資料庫查詢會員名稱
    cursor.execute("SELECT id, name, username FROM member WHERE username = %s AND password = %s", (username, password))
    member = cursor.fetchone()  # 返回的是一個元組或 None
    cursor.close()
    conn.close()

    if member:
        request.session['signed_in'] = True
        request.session['username'] = member[2]  # 存取元組中的 username
        request.session['member_id'] = member[0]  # 存取元組中的 id
        request.session['member_name'] = member[1]  # 存取元組中的 name

        return RedirectResponse(url="/member", status_code=status.HTTP_303_SEE_OTHER)
    else:
        message = "Username or password is not correct"
        return RedirectResponse(url=f"/error?message={message}", status_code=status.HTTP_303_SEE_OTHER)
 
@app.get("/member", response_class=HTMLResponse)
async def member(request: Request):
    # 建立資料庫連接
    conn = mysql.connector.connect(
        host="localhost",
        user="websiteuser",
        password="websitepassword",
        database="website"
    )
    cursor = conn.cursor()
    cursor.execute("""
        SELECT m.content, mem.name, m.like_count, m.time, m.member_id, m.id
        FROM message m
        JOIN member mem ON mem.id = m.member_id
        ORDER BY m.id DESC
    """)
    messages = cursor.fetchall()
    cursor.close()
    conn.close()
    if 'signed_in' in request.session and 'member_name' in request.session:
                # 讀取會話中存儲的用戶資訊
        member_id = request.session.get('member_id')
        member_name = request.session.get('member_name')
        username = request.session.get('username')
        return templates.TemplateResponse("member.html", {"request": request, "member_id": member_id, "member_name": member_name, "username": username, "user_id": member_id, "messages": messages})
    else:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/createMessage")
async def submit_message(request: Request, message: str = Form(...)):
    user_id = request.session.get('member_id')  # 假設會話中存有 member_id
    if not user_id:
        return RedirectResponse(url="/signin", status_code=303)  # 如果未登入則重定向到登入頁

    # 連接數據庫
    conn = mysql.connector.connect(
        host="localhost",
        user="websiteuser",
        password="websitepassword",
        database="website"
    )
    cursor = conn.cursor()
    
    # 插入留言數據
    cursor.execute("INSERT INTO message (member_id, content, like_count, time) VALUES (%s, %s, %s, NOW())", 
                   (user_id, message, 0))
    conn.commit()
    cursor.close()
    conn.close()
    
    return RedirectResponse(url="/member", status_code=303)  # 提交後重定向到會員頁

@app.get("/signout")
async def signout(request: Request):
    # 從會話中移除 signed_in 狀態
    request.session.pop('signed_in', None)
    request.session.pop('username', None)  # 移除用戶名
    request.session.pop('member_name', None)  # 移除會員名稱
    # 重新定向到首頁
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

# 錯誤頁面
@app.get("/error", response_class=HTMLResponse)
async def error(request: Request, message: str):
    return templates.TemplateResponse("error.html", {"request": request, "message": message})

@app.post("/deletemessage/{message_id}")
async def delete_message(request: Request, message_id: int):
    # 檢查用戶是否登入
    if 'member_id' not in request.session:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    user_id = request.session.get('member_id')

    conn = mysql.connector.connect(
        host="localhost",
        user="websiteuser",
        password="websitepassword",
        database="website"
    )
    cursor = conn.cursor()

    # JOIN查詢驗證留言權限
    cursor.execute("""
        SELECT m.id, m.content, m.member_id, mem.name 
        FROM message m
        JOIN member mem ON mem.id = m.member_id
        WHERE m.id = %s AND m.member_id = %s
    """, (message_id, user_id))

    result = cursor.fetchone()

    # 沒有找到留言或留言不屬於當前用戶
    if not result:
        cursor.close()
        conn.close()
        return JSONResponse(status_code=404, content={"detail": "Message not found or access denied"})

    # 如果用戶是留言的所有者，則刪除留言
    cursor.execute("DELETE FROM message WHERE id = %s", (message_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    return RedirectResponse(url="/member", status_code=303)
