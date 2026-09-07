# UI 原型：绿白工作台（设计稿验证用）

- 访问：http://localhost:5456/ui-prototype/index.html（或 /ui-prototype.html 自动跳转）
- 类型：纯 HTML/CSS/JS 静态可点击原型，不依赖后端与 Vue
- 内容：书架 / 书籍工作台（步骤条+章节卡片）/ 章节工作台（编辑器+播放器）/ 任务中心 / 设置
- 交互：左侧工作台导航、面包屑返回、卡片/任务点击跳转、播放动效、试听动效、进度模拟、Toast、键盘左右翻章
- 直达：URL 加 `#book`、`#chapter`、`#jobs`、`#settings` 可直达对应视图

> 注意：该目录属于设计稿产物，正式实现完成后应从 `frontend/public/` 移除，避免进入生产构建。
