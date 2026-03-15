# Visual page

这个目录放前端原型代码。

当前实现：

- `index.html`：工作台页面结构
- `styles.css`：电商运营工作台样式
- `app.js`：调用 `/health`、`/api/chat`、`/api/sessions/{session_id}` 的前端逻辑

访问方式：

1. 启动后端服务：`python main.py serve`
2. 浏览器打开：`http://127.0.0.1:8000/workbench/`

这样前端和后端同源，不需要额外处理 CORS。
