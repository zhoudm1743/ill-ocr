# OCR 识别服务

基于 **FastAPI + RapidOCR (ONNX Runtime)** 的 HTTP OCR 服务，支持通用文字识别与**身份证正反面结构化提取**。

> 生产环境默认部署路径：`/opt/ill-ocr/`  
> 默认端口：`8000`

---

## 目录

- [技术选型](#技术选型)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [部署教程](#部署教程)
- [开发教程](#开发教程)
- [API 文档](#api-文档)
- [运维命令](#运维命令)
- [常见问题](#常见问题)

---

## 技术选型

| 组件 | 说明 |
|------|------|
| [FastAPI](https://fastapi.tiangolo.com/) | HTTP 框架，自带 Swagger 文档 |
| [ONNX Runtime](https://onnxruntime.ai/) | 跨平台推理，CPU 兼容性好 |
| Docker + Compose | 容器化部署 |

---

## 项目结构

```
/opt/ill-ocr/
├── main.py              # FastAPI 入口，路由定义
├── response.py          # 统一响应封装 success / fail
├── idcard_parser.py     # 身份证结构化解析逻辑
├── requirements.txt     # Python 依赖
├── Dockerfile           # 镜像构建
├── docker-compose.yml   # 服务编排
├── logs/                # 日志目录（挂载卷）
└── README.md            # 本文档
```

---

## 环境要求

### 服务器

- Linux（CentOS / Debian / Ubuntu 均可）
- Docker >= 20.10
- Docker Compose V2（`docker compose` 命令）
- 内存建议 >= 2GB（容器限制 4GB）
- CPU >= 2 核（容器限制 4 核）
- 开放端口 `8000`（或按需修改映射）

### 本地开发（可选）

- Python 3.10+
- pip

---

## 部署教程

### 1. 上传项目文件

将以下文件上传到服务器 `/opt/ill-ocr/`：

```bash
mkdir -p /opt/ill-ocr/logs
# 上传：main.py idcard_parser.py requirements.txt Dockerfile docker-compose.yml
```

### 2. 构建镜像

```bash
cd /opt/ill-ocr
docker compose build --no-cache
```

首次构建约 **3～5 分钟**（使用阿里云 apt 源 + 清华 pip 源）。  
构建过程会安装系统依赖和 Python 包，**不会**在构建阶段预下载 OCR 模型（避免 segfault）。

> 如需保存构建日志：
> ```bash
> docker compose build --no-cache 2>&1 | tee build.log
> ```

### 3. 启动服务

```bash
docker compose up -d
```

### 4. 验证

等待约 10～15 秒（RapidOCR 引擎初始化），然后：

```bash
# 健康检查
curl -s http://localhost:8000/health
# 期望：{"status":"ok","ready":true}

# 查看容器状态
docker ps --filter name=ill-ocr

# 查看启动日志
docker logs ill-ocr --tail 20
```

### 5. 功能测试

```bash
# 通用 OCR
curl -s -X POST http://localhost:8000/ocr/upload -F "file=@test.jpg"

# 身份证正面
curl -s -X POST http://localhost:8000/ocr/idcard/front -F "file=@id_front.jpg"

# 身份证反面
curl -s -X POST http://localhost:8000/ocr/idcard/back -F "file=@id_back.jpg"
```

### 6. 访问 Swagger 文档

浏览器打开：

```
http://<服务器IP>:8000/docs
```

### 7. 更新代码（不重建镜像）

如果只修改了 Python 文件（`main.py` / `idcard_parser.py`），可以热更新：

```bash
docker cp /opt/ill-ocr/main.py ill-ocr:/app/main.py
docker cp /opt/ill-ocr/response.py ill-ocr:/app/response.py
docker cp /opt/ill-ocr/idcard_parser.py ill-ocr:/app/idcard_parser.py
docker restart ill-ocr
```

如果修改了 `requirements.txt` 或 `Dockerfile`，需要重新构建：

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## 开发教程

### 本地运行（不用 Docker）

```bash
cd /opt/ill-ocr   # 或你的本地项目目录

# 创建虚拟环境（推荐）
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 启动开发服务器（热重载）
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

访问 `http://localhost:8000/docs` 调试接口。

### 代码架构

```
请求 → FastAPI 路由 (main.py)
         ↓
     图片解码 (_bytes_to_ndarray)
         ↓
     RapidOCR 识别 (_run_ocr，线程池异步执行)
         ↓
     通用 OCR：直接返回文字块列表
     身份证 OCR：idcard_parser.py 结构化提取字段
```

**关键设计点：**

1. **全局单例引擎**：在 `lifespan` 中初始化 `RapidOCR()`，避免每次请求重复加载模型
2. **异步不阻塞**：OCR 是 CPU 密集型，通过 `run_in_executor` 放到线程池
3. **结构化解析独立模块**：`idcard_parser.py` 与 HTTP 层解耦，便于单元测试和扩展

### 新增接口示例

在 `main.py` 中添加路由：

```python
@app.post("/ocr/invoice")
async def ocr_invoice(file: UploadFile = File(...)):
    data = await file.read()
    img = _bytes_to_ndarray(data)
    items = await _ocr_async(img)
    # 在此调用你的解析逻辑
    return {"count": len(items), "results": items}
```

### 扩展身份证解析

编辑 `idcard_parser.py`：

- `parse_idcard_front()` — 正面字段提取
- `parse_idcard_back()` — 反面字段提取
- `detect_side()` — 自动判断正反面

字段提取策略：

1. 正则匹配（身份证号、日期、有效期等固定格式）
2. 标签定位（在「姓名」「住址」等关键字后取相邻文本块）
3. 坐标排序（按 y/x 坐标合并多行地址）

添加新证件类型（如营业执照）时，建议新建 `biz_license_parser.py`，保持模块独立。

### 本地调试身份证解析（无需 OCR）

```python
# test_idcard.py
from idcard_parser import parse_idcard_front

mock_items = [
    {"text": "姓名", "confidence": 0.99, "box": [[0,0],[0,0],[0,0],[0,0]]},
    {"text": "张三", "confidence": 0.98, "box": [[0,0],[0,0],[0,0],[0,0]]},
    {"text": "性别男", "confidence": 0.99, "box": [[0,0],[0,0],[0,0],[0,0]]},
    {"text": "450881199706210314", "confidence": 0.99, "box": [[0,0],[0,0],[0,0],[0,0]]},
]
print(parse_idcard_front(mock_items))
```

---

## 统一响应格式

所有接口均返回统一 JSON 结构：

**成功：**

```json
{
  "code": 200,
  "data": { ... },
  "message": "ok"
}
```

**失败：**

```json
{
  "code": 400,
  "data": null,
  "message": "错误消息"
}
```

- 成功时 HTTP 状态码为 `200`，业务码 `code` 也为 `200`
- 失败时 HTTP 状态码与 `code` 一致（如 400、422、500）
- 封装实现见 `response.py` 中的 `success()` / `fail()` 及全局异常处理

---

## API 文档

### 统一响应格式

**成功：**

```json
{
  "code": 200,
  "data": { ... },
  "message": "ok"
}
```

**失败：**

```json
{
  "code": 400,
  "data": null,
  "message": "错误消息"
}
```

- HTTP 状态码与 body 中的 `code` 保持一致（成功时 HTTP 200）
- 业务数据均在 `data` 字段中，不再直接平铺在根级

---

### 健康检查

```
GET /health
```

响应：

```json
{
  "code": 200,
  "data": { "status": "ok", "ready": true },
  "message": "ok"
}
```

---

### 通用 OCR

#### 文件上传

```
POST /ocr/upload
Content-Type: multipart/form-data
```

| 参数 | 类型 | 说明 |
|------|------|------|
| file | File | 图片文件（jpg/png/webp 等） |

响应：

```json
{
  "code": 200,
  "data": {
    "count": 3,
    "results": [
      {
        "text": "识别文字",
        "confidence": 0.9876,
        "box": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
      }
    ]
  },
  "message": "ok"
}
```

#### Base64 上传

```
POST /ocr/base64
Content-Type: application/json
```

```json
{
  "image": "data:image/png;base64,iVBORw0KGgo..."
}
```

---

### 身份证 OCR

#### 自动识别正反面

```
POST /ocr/idcard?side=auto&include_raw=false
Content-Type: multipart/form-data
```

| Query 参数 | 默认值 | 说明 |
|------------|--------|------|
| side | auto | `front` / `back` / `auto` |
| include_raw | false | 是否附带原始 OCR 行结果 |

#### 身份证正面

```
POST /ocr/idcard/front
```

响应：

```json
{
  "code": 200,
  "data": {
    "side": "front",
    "fields": {
      "name": "周东明",
      "gender": "男",
      "ethnicity": "汉",
      "birth_date": "1997年6月21日",
      "birth_date_iso": "1997-06-21",
      "address": "广西桂平市木乐镇罗贤村横冲屯27号",
      "id_number": "450881199706210314"
    },
    "confidence": {
      "name": 0.9997,
      "gender": 0.9928,
      "ethnicity": 0.9978,
      "birth_date": 0.9998,
      "address": 0.991,
      "id_number": 0.9983
    },
    "raw_count": 19
  },
  "message": "ok"
}
```

#### 身份证反面

```
POST /ocr/idcard/back
```

响应：

```json
{
  "code": 200,
  "data": {
    "side": "back",
    "fields": {
      "issue_authority": "桂平市公安局",
      "valid_period": "2024.03.01-2044.03.01",
      "valid_start": "2024.03.01",
      "valid_end": "2044.03.01",
      "is_long_term": false
    },
    "confidence": {
      "issue_authority": 0.9989,
      "valid_period": 0.9995
    },
    "raw_count": 8
  },
  "message": "ok"
}
```

#### Base64 方式

```
POST /ocr/idcard/base64?include_raw=false
Content-Type: application/json
```

```json
{
  "image": "data:image/jpeg;base64,...",
  "side": "front"
}
```

---

### 前端调用示例（JavaScript）

```javascript
async function ocrIdCardFront(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('http://your-server:8000/ocr/idcard/front', {
    method: 'POST',
    body: form,
  })
  const json = await res.json()
  if (json.code !== 200) throw new Error(json.message)
  return json.data
}

// 使用
const input = document.querySelector('input[type=file]')
input.addEventListener('change', async (e) => {
  const data = await ocrIdCardFront(e.target.files[0])
  console.log(data.fields.name)       // 姓名
  console.log(data.fields.id_number)  // 身份证号
})
```

### Go 后端调用示例

```go
func ocrIdCardFront(imagePath string) (map[string]interface{}, error) {
    file, err := os.Open(imagePath)
    if err != nil {
        return nil, err
    }
    defer file.Close()

    body := &bytes.Buffer{}
    writer := multipart.NewWriter(body)
    part, _ := writer.CreateFormFile("file", filepath.Base(imagePath))
    io.Copy(part, file)
    writer.Close()

    req, _ := http.NewRequest("POST", "http://your-server:8000/ocr/idcard/front", body)
    req.Header.Set("Content-Type", writer.FormDataContentType())

    resp, err := http.DefaultClient.Do(req)
    // ... 解析 JSON
}
```

---

## 运维命令

```bash
# 启动
docker compose up -d

# 停止
docker compose stop

# 重启
docker restart ill-ocr

# 查看日志（实时）
docker logs -f ill-ocr

# 查看资源占用
docker stats ill-ocr

# 进入容器调试
docker exec -it ill-ocr bash

# 完全销毁（含 volume，慎用）
docker compose down -v
```

### 修改端口

编辑 `docker-compose.yml`：

```yaml
ports:
  - "9000:8000"   # 宿主机 9000 → 容器 8000
```

### 配置资源限制

`docker-compose.yml` 中已设置：

```yaml
deploy:
  resources:
    limits:
      cpus: "4"
      memory: 4G
```

---

## 常见问题

### Q: 构建时 apt 下载很慢？

Dockerfile 已配置阿里云 apt 镜像源。若仍慢，检查服务器网络或换用其他国内源。

### Q: 构建报错 `libgl1-mesa-glx has no installation candidate`？

Debian 13 (Trixie) 已将包名改为 `libgl1`，当前 Dockerfile 已修复。

### Q: 请求返回 `Internal Server Error`？

查看日志：

```bash
docker logs ill-ocr --tail 50
```

常见原因：图片格式不支持、图片为空、引擎未就绪（等待 `/health` 返回 `ready: true`）。

### Q: 身份证地址字段多了乱码？

身份证上的壮文拼音可能被 OCR 识别进来。`idcard_parser.py` 已过滤非中文地址后缀，若仍有问题可调整 `_clean_address()` 规则。

### Q: 识别准确率不够？

建议：

1. 使用清晰、正拍、无强反光的图片
2. 图片分辨率 >= 800px 宽
3. 开启 `include_raw=true` 查看原始 OCR 结果，排查是识别问题还是解析问题
4. 如需更高精度，可换 RapidOCR 的 server 版 ONNX 模型（需修改 RapidOCR 初始化参数）

### Q: 如何接入 Sioyun 业务系统？

1. 在后端 `config.yaml` 增加 OCR 服务地址配置
2. 封装 HTTP 客户端调用 `/ocr/idcard/front` 和 `/ocr/idcard/back`
3. 前端上传证件照后调用后端接口，将返回的 `fields` 回填表单

---

## 版本记录

| 版本 | 说明 |
|------|------|
| 1.0.0 | 初始版本，通用 OCR（RapidOCR + FastAPI） |
| 1.2.0 | 统一响应格式 `{code, data, message}`，新增 `response.py` |
