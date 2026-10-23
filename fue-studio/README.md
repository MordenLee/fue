# FUE Studio

桌面应用，负责资料库界面、聊天交互和 Core 连接。业务与数据由独立 Core 管理，宿主接入由 Skill 提供。

`src/main` 管理桌面生命周期、安装与连接；`src/preload` 暴露 IPC；`src/renderer` 是 React 界面。这三个目录是 Electron 的内部职责划分，不是另一套前后端工程。

界面依赖只在本目录声明，根目录不再重复安装。设置页提供资料库状态、下次启动切换、Skill 安装/更新和连接检测。聊天执行面板可查询原任务；断线不会自动再次生成回答。写作原型保留但默认不加载。

详见 [实施架构](../docs/design/core-studio-skill-implementation.md) 与 [安装说明](../docs/design/installation-and-workspaces.md)。

## Recommended IDE Setup

- [VSCode](https://code.visualstudio.com/) + [ESLint](https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint) + [Prettier](https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode)

## Project Setup

### Install

```bash
$ npm install
```

### Development

```bash
$ npm run dev
```

### Build

```bash
# For windows
$ npm run build:win

# For macOS
$ npm run build:mac

# For Linux
$ npm run build:linux
```
