# skill-service

Skill 技能管理服务（独立进程，独占 MySQL，对外暴露 REST API）。

## 启动

```bash
cd skill-service
cp .env.example .env  # 配置 MySQL 连接
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

## API

| 方法 & 路径 | 用途 |
|---|---|
| `GET /health` | 健康检查 |
| `GET /skills/descriptors` | 拉取全部 descriptor + 版本号（各后端读路径） |
| `GET /skills` | 列出全部技能（侧栏 + slash 自动补全） |
| `GET /skills/{name}` | 技能详情（含正文） |
| `POST /skills` | 创建自定义技能 |
| `PUT /skills/{name}` | 编辑自定义技能 |
| `PATCH /skills/{name}/enabled` | 启用/停用 |
| `DELETE /skills/{name}` | 删除自定义技能 |

## 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MYSQL_HOST` | `127.0.0.1` | MySQL 主机 |
| `MYSQL_PORT` | `3306` | MySQL 端口 |
| `MYSQL_USER` | `root` | MySQL 用户 |
| `MYSQL_PASSWORD` | `` | MySQL 密码 |
| `MYSQL_DATABASE` | `default` | 数据库名 |
