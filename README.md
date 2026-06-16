# TTF 字体转换工具

一个 FastAPI 在线工具，支持上传 `.ttf` 字体，按百分比缩放字形，并可选择加粗后下载转换结果。

## 功能

- 上传 `.ttf` 字体文件
- 缩放范围：10% 到 300%
- 字形转换：不处理、Thin 变细、Bold 加粗
- 水平效果和垂直效果都由用户输入，范围：-50 到 50，按字体 `unitsPerEm` 的百分比换算成实际字形单位
- 转换完成后显示下载按钮，用户点击后下载
- 输出文件名自动按 `原文件名-缩放比例pct-效果-x水平-y垂直.ttf` 生成
- 转换结果直接作为 `.ttf` 下载
- 服务端只做请求内处理，不永久保存上传文件或结果文件

## 本地运行

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 测试

```powershell
python -m pytest -v
```

## 部署建议

生产环境建议用 Nginx 反向代理到 Uvicorn/Gunicorn。

示例 Uvicorn 命令：

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Nginx 上传大小要和应用限制保持一致：

```nginx
client_max_body_size 50m;
```

接口会拒绝超过 50MB 的字体文件。服务器不会长期保存字体；当前实现直接在内存中读取、转换并返回下载响应。

## 宝塔面板部署

以下假设域名解析已经指向服务器，宝塔里已经安装 Nginx。

1. 在宝塔文件管理里创建项目目录：

```bash
/www/wwwroot/font-tool
```

2. 把本项目所有文件上传到这个目录，确保目录里能看到：

```text
main.py
font_processor.py
requirements.txt
templates/
static/
```

3. 在宝塔终端执行：

```bash
cd /www/wwwroot/font-tool
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python -m pytest -v
```

4. 先手动试跑：

```bash
cd /www/wwwroot/font-tool
source venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

如果终端显示 Uvicorn running，说明后端正常。按 `Ctrl+C` 停止，然后交给进程管理器常驻运行。

5. 在宝塔软件商店安装并打开“Supervisor管理器”，添加守护进程：

```text
名称：font-tool
运行目录：/www/wwwroot/font-tool
启动命令：/www/wwwroot/font-tool/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
运行用户：www
```

启动后确认状态为运行中。

6. 在宝塔“网站”里添加你的域名站点，然后进入站点设置，添加反向代理：

```text
目标 URL：http://127.0.0.1:8001
发送域名：$host
```

如果手动编辑 Nginx 配置，可以使用：

```nginx
client_max_body_size 50m;

location / {
    proxy_pass http://127.0.0.1:8001;
    proxy_connect_timeout 60s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
    proxy_buffering off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

如果使用 20MB 以上字体并开启 Bold 100 这类高强度整体加粗，转换可能超过 1 分钟。宝塔反向代理里也需要把“连接超时/响应超时”调到 300 秒左右，否则 Nginx 可能先返回 504。

7. 在宝塔站点 SSL 页面申请或导入证书，开启 HTTPS。

8. 浏览器访问你的域名测试上传、转换和下载。

注意：Uvicorn 只绑定 `127.0.0.1:8001`，不需要在安全组或宝塔防火墙开放 `8001`。公网只开放 `80/443` 即可。

## 文件结构

```text
main.py                 FastAPI 入口、上传接口、输出文件名生成
font_processor.py       TTF 缩放、Thin/Bold 字形转换逻辑
templates/index.html    前端页面
static/styles.css       页面样式
static/app.js           上传和下载交互
tests/                  自动化测试
```
