# 玖能官网 v0.4 上线部署手册(Render 免费层,0 成本)

> 本文档是给 pi agent / 开发者照着执行的操作手册。目标:把 `开发版v0.4`(React+Vite+Express+Gemini 询价)部署到 Render 免费层,公网可访问。
> 前置:GitHub 账号(miiinniam)、Render 账号(GitHub 登录即可)、GEMINI_API_KEY。

---

## 第一步:git 初始化 + 推送 GitHub

本项目目前不是 git 仓库,必须先建仓,Render 需要从 GitHub 拉代码。

```bash
cd "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4"

# 1. 初始化仓库
git init
git add -A
git commit -m "玖能官网 v0.4 初始提交"

# 2. 检查 .gitignore 是否覆盖了密钥(应包含 node_modules/、dist/、.env*)
cat .gitignore   # 已有:node_modules/ dist/ .env* 等,OK

# 3. 建 GitHub 仓库并推送(仓库名 jiuneng-website,public)
git remote add origin https://github.com/miiinniam/jiuneng-website.git
git branch -M main
git push -u origin main
```

> ⚠️ public/ 有 39MB 图片,首次 push 会稍慢,属正常。GitHub 单文件 100MB 限制内,无需处理。
> ⚠️ 若 GitHub token 未缓存:用 `git credential fill <<< $'protocol=https\nhost=github.com\n'` 提取缓存 token,或让用户在 GitHub 生成 PAT。

## 第二步:Render 创建服务(Blueprint 声明式)

render.yaml 已在仓库根,一条路部署:

1. 打开 https://dashboard.render.com → **New → Blueprint**
2. 连接 GitHub,选择 `miiinniam/jiuneng-website`
3. Render 自动读取 `render.yaml`,显示服务 `jiuneng-website`(runtime: node,plan: free)
4. 点击 **Apply / Create Resources** → 等待构建(约 2-4 分钟)
5. 构建成功后得到 URL:`https://jiuneng-website.onrender.com`

> 若不用 Blueprint,也可手动 New → Web Service → 选仓库 → Runtime=Node → Build Command=`npm run build` → Start Command=`npm start` → Plan=Free,效果相同。

## 第三步:填环境变量(最关键,漏了 AI 询价就挂)

Render 服务页 → **Settings → Environment**:

| 变量 | 值 |
|---|---|
| `GEMINI_API_KEY` | ⚠️ **必填**,Gemini API 密钥(render.yaml 里 `sync: false`,必须手动填) |
| `APP_URL` | 可选,填 `https://jiuneng-website.onrender.com` |
| `NODE_ENV` | render.yaml 已配 `production`,面板里应能看到 |

然后 **Manual Deploy → Deploy latest commit** 触发一次重部署让环境变量生效。

## 第四步:验证上线

```bash
# 健康检查(核心)
curl https://jiuneng-website.onrender.com/api/health
# 期望:{"status":"ok","time":"..."}

# 页面
curl -sI https://jiuneng-website.onrender.com/ | head -3
# 期望:HTTP/1.1 200

# AI 询价接口(带真实 GEMINI_API_KEY 时才 200)
curl -s -X POST https://jiuneng-website.onrender.com/api/logistics-consult \
  -H "Content-Type: application/json" \
  -d '{"name":"测试","details":"从友谊关运一批设备到河内"}' | head -c 300
# 期望:JSON 含 routeRecommendation 等字段;若 500 说明 GEMINI_API_KEY 没生效
```

## 第五步:保活(免费层必备)

Render 免费实例 **15 分钟无请求即休眠**,休眠后第一个请求被拒(404/超时),唤醒需 5-15s。低频官网场景必须保活。

**推荐:UptimeRobot(云端,生产级)**
1. 注册 https://uptimerobot.com(免费版够用)
2. Add New Monitor → HTTP(S) → URL=`https://jiuneng-website.onrender.com/api/health` → Interval=5 分钟
3. 云端跑,不依赖本机开机

**备选:本机 Hermes cron**(开发期可,电脑关机即失效)
- `~/AppData/Local/hermes/scripts/render_keepalive.py`,每 10 分钟 GET `/api/health`
- ⚠️ 必须用 .py 文件(Windows 上 .sh 反斜杠路径会被吞),脚本模板见 osrmpp-dev 技能

## 第六步(可选):绑定 jiuneng.space 子域

根域 `jiuneng.space` 目前在 Vercel(OSRM++ 官网),**不要动根域解析**。要绑子域(如 `www.jiuneng.space` 或 `site.jiuneng.space`):

1. Render 服务 → **Settings → Custom Domains** → Add Domain → 填子域名
2. 在域名 DNS 服务商加 CNAME:`<子域>` → `jiuneng-website.onrender.com`
3. Render 自动签 HTTPS 证书(几分钟)
4. 更新 `APP_URL` 环境变量 → 重部署

## 后续更新流程(每次改代码后)

```bash
cd "D:/01_业务/玖能/JIUNENG 企业背景建设/JIUNENG 官网/开发版v0.4"
npm run lint        # 类型检查(必须通过)
npm run build       # 本地构建验证(必须通过)
git add -A && git commit -m "描述"
git push            # GitHub 推送 → Render 自动重部署(git push 触发)
curl https://jiuneng-website.onrender.com/api/health   # 等 2-3 分钟构建完再验
```

> ⚠️ 若 git push 没有触发 Render 自动部署:去 Render 服务 Settings → 确认 GitHub 连接正常,或 Manual Deploy。

## 回滚

Render 服务页 → **Events** → 找到上次正常部署 → **Deploy** 即可回滚到该版本。

---

## 故障排查速查

| 症状 | 原因 | 处理 |
|---|---|---|
| `/api/health` 404/超时,等一会又 200 | 免费层休眠 | 配保活(第五步),非代码 bug |
| 页面 200 但 AI 询价 500 | GEMINI_API_KEY 缺失/错误 | 检查环境变量 → Manual Deploy |
| 页面样式全乱/白屏 | NODE_ENV 不是 production(走了 dev 中间件) | 确认 render.yaml 的 NODE_ENV=production 生效 |
| 构建失败 dist 不存在 | npm install 未装全/构建命令错 | 确认 Build Command=`npm run build` |
| 中文路径报错 | Windows 本地路径含中文 | Render 上无此问题;本地用 `cd` 到目录再操作 |
