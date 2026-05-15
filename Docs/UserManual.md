# Campus Login 用户手册

## 安装与运行
- 运行 `dist\CampusLogin.exe`（Python版本）或构建后 `dist-native\CampusLogin.exe`（原生版本）。
- 静默登录：在命令行执行 `CampusLogin.exe --silent`。

## 主要功能
- 多账户管理、配置导入/导出、保持联网、掉线自动连接校园网、夜间模式、系统托盘与通知。

## 使用步骤
- 在“登录”页输入账号、密码与运营商，勾选“记住密码”后即可启用“自动登录”和“保持联网”。
- 点击“导入配置/导出配置”进行配置迁移。
- 勾选“开机自启”自动注册计划任务，开机约 30 秒后执行静默登录。

## 构建原生 EXE
- 安装 .NET SDK 后，运行 `powershell -ExecutionPolicy Bypass -File Build\build_dotnet.ps1`，生成 `dist-native\CampusLogin.exe`。

## 生成 MSI
- 安装 WiX Toolset（管理员），执行：
  - `candle.exe Build\wix\Product.wxs -o Build\wix\Product.wixobj`
  - `light.exe Build\wix\Product.wixobj -o Build\CampusLogin.msi -ext WixUIExtension -dWixUILicenseRtf=Build\wix\License.rtf`
- 静默安装：`msiexec /i Build\CampusLogin.msi /qn`

## 问题反馈
- 无网络或登录失败会显示托盘气泡提示，检查账号、密码与网络环境后重试。
