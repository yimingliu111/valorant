# 指尖元素特效（风之飞镖 / 火球）

摄像头实时特效，两种元素可随时切换（按 1 / 2，网页版点右上角按钮）：

- **风之飞镖**：竖起食指时，黑银叶形飞镖出现并**持续绕着指尖旋转飞行**
  （风灵法阵、绿色光点粒子，首次召唤有「风来！」闪现），手不动它就一直转
- **火球**：**摊开手掌**（五指张开）时，掌心上方燃起熊熊火球
  （旋转火环、摇曳火舌、白热光球、上升余烬，出现瞬间爆燃），收拢手掌即熄

两种元素均支持两只手同时各一个。

两个版本，效果相同，任选其一：

## 版本一：后端 Python 本地版（`backend/`，推荐配合 VSCode 使用）

纯本地运行，浏览器都不用开。适合 macOS（含 M 系列芯片）/ Windows / Linux。

### 首次准备（只需一次）

```bash
cd sword-finger
python3 -m venv venv          # 创建虚拟环境
source venv/bin/activate      # Windows 是 venv\Scripts\activate
pip install -r backend/requirements.txt
```

> 模型文件 `backend/hand_landmarker.task` 已就位，无需再下载。

### 运行

```bash
cd backend
python sword_finger.py
```

- 按 **Q** 或 **ESC** 退出，或直接关闭窗口
- macOS 首次运行会弹出摄像头权限请求，点允许；
  若没弹窗，去「系统设置 → 隐私与安全性 → 相机」给 **终端 / VSCode** 授权

### Python 版可调参数（`backend/element_dart.py` 顶部）

| 想改什么 | 参数 |
|---|---|
| 旋转速度 | `SPIN_SPEED` |
| 指向前方的判定阈值 | `POINT_ENTER` / `POINT_EXIT`（指尖-手腕投影长度，越小要求指得越正） |
| 公转半径 / 速度 | `ORBIT_RADIUS` / `ORBIT_SPEED` |
| 发射冷却 | `LAUNCH_COOLDOWN` |
| 冲向观看者的时长 | `RUSH_TIME` |
| 飞镖的样式（颜色/形状） | `build_dart_sprite()` |

## 版本二：前端网页版（`frontend/`）

本地预览：

```bash
cd frontend
python3 -m http.server 8765
```

浏览器打开 <http://localhost:8765>（摄像头权限需要 localhost 或 HTTPS）。
无摄像头时打开 <http://localhost:8765/?demo> 看演示。

网页版全部逻辑在 `frontend/index.html` 单文件里：手势判定在 `updateFromHands`，
公转/发射在 `launchSword` / `updateFly`，飞镖造型在 `drawSwordOnce`，
火球在 `drawFireball`，元素切换在 `setElement`。

## 部署到网上（让别人也能打开）

网页版是零后端的单文件页面（模型从 CDN 加载、识别全部在访客浏览器里完成），
把它传到任何**支持 HTTPS 的免费静态托管**即可，代码不用改。

- **硬性要求只有一条**：必须是 HTTPS，否则浏览器不允许调用摄像头
  （localhost 例外，所以本地预览才用 http.server）
- MediaPipe 模型（约 7MB）在首次打开时从 Google 的 CDN 下载，托管平台不需要存它

### 方式一：Netlify Drop（最快，不用命令行）

1. 打开 <https://app.netlify.com/drop>，注册/登录（免费）
2. 把 `frontend` 文件夹（里面就一个 `index.html`）拖进网页
3. 几秒后得到一个 `https://xxx.netlify.app` 网址，直接分享

### 方式二：GitHub Pages（免费、长期稳定）

```bash
cd frontend
git init && git add index.html && git commit -m "指尖元素网页版"
# 在 GitHub 建一个空仓库后：
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

然后在该仓库的 **Settings → Pages** 里把分支设为 `main`，保存。
一两分钟后得到 `https://<用户名>.github.io/<仓库名>/`。

### 部署后

- 手机也能用：用手机浏览器打开同一个网址，调用的是手机前置摄像头，
  举着手玩反而更方便
- 顺带一提 Python 版没法这样"上云"——它依赖本机摄像头；浏览器版已经把
  识别全部放在访客端，不需要也不建议做成服务器运算

## 目录结构

```
sword-finger/
├── backend/                 # 后端：Python 本地版（OpenCV + MediaPipe）
│   ├── sword_finger.py      #   主程序：摄像头、手部检测、元素调度与切换
│   ├── element_dart.py      #   飞镖元素：造型、绕指尖旋转飞行
│   ├── element_fire.py      #   火球元素：摊手检测、火焰绘制
│   ├── fx_common.py         #   公共工具：精灵叠加、光斑、文字渲染、冲击波
│   ├── hand_landmarker.task #   MediaPipe 手部关键点模型（21 点）
│   └── requirements.txt     #   依赖清单
├── frontend/                # 前端：网页版（单文件，零后端，可直接部署）
│   └── index.html
├── picture/                 # 参考图（你提供的造型图）
├── previews/                # 开发过程中的验证截图（可删）
├── venv/                    # Python 虚拟环境（根目录，两端共用）
└── README.md
```

> 前后端互不依赖：只玩网页版可以不动 `backend/`；反之亦然。
> 两端都是"元素注册表"结构，加新元素都不用碰框架代码：
> - 后端：照 `backend/element_fire.py` 写一个类（update / draw_hold / reset），
>   在 `sword_finger.py` 的 elements 里注册按键即可
> - 前端：在 `frontend/index.html` 的 ELEMENTS 里加一个对象
>   （update / drawHold / label / hint），切换按钮会自动生成

## 常见问题

- **窗口黑屏 / 打不开摄像头**：几乎都是没给摄像头权限，见上方 macOS 授权步骤
- **pip 安装超时**：网络问题，重跑 `pip install -r backend/requirements.txt`（支持断点续传）；
  也可换镜像源：`pip install -r backend/requirements.txt -i https://mirrors.aliyun.com/pypi/simple/`
- **识别不到手**：光线别太暗，手离摄像头 30–80cm，指尖朝上
- **报 Metal / GPU 相关崩溃**：请在**本机的普通终端或 VSCode 内置终端**里运行
  （SSH / 远程会话拿不到图形服务，MediaPipe 会初始化失败）
