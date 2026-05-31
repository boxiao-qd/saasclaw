#!/usr/bin/env bash
# =============================================================================
# Super-Agent 一键部署脚本
# =============================================================================
# 用法:
#   ./deploy.sh              # 交互模式，检查依赖并部署
#   ./deploy.sh --full       # 全部服务（含前端 nginx）部署到 Docker
#   ./deploy.sh --status     # 查看各服务状态
#   ./deploy.sh --stop       # 停止所有服务
#
# 组件清单:
#   MySQL 8.0      :3307    — 业务数据库
#   Redis 7        :6380    — 缓存 / Celery broker
#   Elasticsearch  :9201    — 消息全文搜索
#   MinIO          :9002    — 对象存储 (API) / :9003 (Console)
#   FastAPI        :8001    — 后端 API
#   Celery Beat    (内部)    — 定时任务调度器
#   Celery Worker  (内部)    — 定时任务执行器（HTTP 分发）
#   Nginx          :3001    — 前端静态文件 + API 反代
# =============================================================================

set -euo pipefail

# ── 配置 ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PROJECT_ROOT="$SCRIPT_DIR"
FRONTEND_DIR="$PROJECT_ROOT/frontend/super-agent-chatui"
SCHEDULER_DIR="$PROJECT_ROOT/scheduler"

# 颜色输出
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo -e "\n${BLUE}═══ $* ═══${NC}"; }

# ── 帮助 ────────────────────────────────────────────────
usage() {
    cat <<EOF
Super-Agent 一键部署脚本

用法: $0 [命令]

命令:
  (无参数)     交互模式，检测依赖、配置环境、启动服务
  --full       全部服务部署到 Docker（含前端 nginx）
  --status     查看所有服务运行状态
  --stop       停止所有服务
  --help       显示此帮助

首次部署流程:
  1. 检测 Docker / Python / Node.js
  2. 创建 .env（如不存在）
  3. 启动基础设施（MySQL, Redis, ES, MinIO）
  4. 安装 Python 依赖并启动 FastAPI
  5. 构建前端
  6. 启动调度器
  7. 启动 Nginx 前端服务
EOF
    exit 0
}

# ── 依赖检查 ────────────────────────────────────────────
check_prerequisites() {
    step "检查运行环境"

    local missing=0

    if ! command -v docker &>/dev/null; then
        err "未找到 docker，请先安装 Docker"
        missing=1
    else
        info "docker: $(docker --version)"
    fi

    if ! docker compose version &>/dev/null; then
        err "未找到 docker compose，请先安装 Docker Compose"
        missing=1
    else
        info "docker compose: $(docker compose version)"
    fi

    if ! command -v python3 &>/dev/null; then
        err "未找到 python3，请先安装 Python 3.11+"
        missing=1
    else
        info "python: $(python3 --version)"
    fi

    if ! command -v node &>/dev/null; then
        err "未找到 node，请先安装 Node.js 18+"
        missing=1
    else
        info "node: $(node --version)"
    fi

    if ! command -v npm &>/dev/null; then
        err "未找到 npm"
        missing=1
    else
        info "npm: $(npm --version)"
    fi

    if [ $missing -ne 0 ]; then
        err "缺少必要依赖，请先安装后再运行。"
        exit 1
    fi
    info "环境检查通过"
}

# ── .env 初始化 ─────────────────────────────────────────
setup_env() {
    step "配置环境变量"

    if [ -f "$PROJECT_ROOT/.env" ]; then
        info ".env 已存在，跳过创建"
        # 确保有 INTERNAL_API_TOKEN
        if ! grep -q "INTERNAL_API_TOKEN" "$PROJECT_ROOT/.env" || grep -q 'INTERNAL_API_TOKEN=$' "$PROJECT_ROOT/.env"; then
            local token
            token=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 2>/dev/null || date +%s | sha256sum | cut -d' ' -f1)
            if grep -q "INTERNAL_API_TOKEN=" "$PROJECT_ROOT/.env"; then
                sed -i '' "s/INTERNAL_API_TOKEN=.*/INTERNAL_API_TOKEN=$token/" "$PROJECT_ROOT/.env"
            else
                echo "INTERNAL_API_TOKEN=$token" >> "$PROJECT_ROOT/.env"
            fi
            info "已生成 INTERNAL_API_TOKEN"
        fi
    else
        warn ".env 不存在，从模板创建..."
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        else
            err "未找到 .env.example 模板文件"
            exit 1
        fi
        # 生成随机 token
        local token
        token=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 2>/dev/null || date +%s | sha256sum | cut -d' ' -f1)
        sed -i '' "s/INTERNAL_API_TOKEN=.*/INTERNAL_API_TOKEN=$token/" "$PROJECT_ROOT/.env"
        # 生成 JWT secret
        local jwt_secret
        jwt_secret=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32 2>/dev/null || date +%s | sha256sum | cut -d' ' -f1)
        sed -i '' "s/JWT_SECRET=.*/JWT_SECRET=$jwt_secret/" "$PROJECT_ROOT/.env"

        warn "⚠️  请编辑 .env 文件，至少配置以下项："
        warn "  - OPENAI_API_BASE     LLM API 地址"
        warn "  - OPENAI_API_KEYS     LLM API 密钥"
        warn "  - DEFAULT_MODEL       默认模型"
        echo ""
        read -rp "是否现在就编辑 .env？(y/n) " choice
        if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
            ${EDITOR:-vi} "$PROJECT_ROOT/.env"
        fi
    fi

    # 同步调度器 .env 中的 INTERNAL_API_TOKEN
    local token
    token=$(grep "^INTERNAL_API_TOKEN=" "$PROJECT_ROOT/.env" | cut -d'=' -f2-)
    if [ -n "$token" ]; then
        if [ -f "$SCHEDULER_DIR/.env" ]; then
            sed -i '' "s/INTERNAL_API_TOKEN=.*/INTERNAL_API_TOKEN=$token/" "$SCHEDULER_DIR/.env"
        fi
        info "调度器 token 已同步"
    fi
}

# ── 启动基础设施 ────────────────────────────────────────
start_infra() {
    step "启动基础设施 (MySQL, Redis, ES, MinIO)"

    docker compose up -d mysql redis elasticsearch minio

    info "等待 MySQL 就绪..."
    for i in $(seq 1 30); do
        if docker exec lucid-mysql mysqladmin ping -h localhost --silent 2>/dev/null; then
            info "MySQL 已就绪"
            break
        fi
        if [ $i -eq 30 ]; then
            err "MySQL 启动超时，请检查 docker logs lucid-mysql"
            exit 1
        fi
        sleep 2
    done

    info "等待 Redis 就绪..."
    for i in $(seq 1 15); do
        if docker exec lucid-redis redis-cli ping 2>/dev/null | grep -q PONG; then
            info "Redis 已就绪"
            break
        fi
        sleep 2
    done
}

# ── 启动 FastAPI ────────────────────────────────────────
start_fastapi() {
    step "启动 FastAPI 后端"

    # 检查是否已有 fastapi 容器在运行
    if docker ps --format '{{.Names}}' | grep -q '^lucid-fastapi$'; then
        info "lucid-fastapi 容器已在运行"
        return
    fi

    # 创建独立虚拟环境，避免与其他项目的依赖冲突
    if [ ! -d "$PROJECT_ROOT/.venv" ]; then
        info "创建虚拟环境 .venv ..."
        python3 -m venv "$PROJECT_ROOT/.venv"
    fi

    info "安装 Python 依赖..."
    "$PROJECT_ROOT/.venv/bin/pip" install -r "$PROJECT_ROOT/requirements.txt" -q

    # 数据库表自动创建（FastAPI 启动时执行 init_db）
    info "启动 FastAPI (uvicorn :8001)..."
    nohup "$PROJECT_ROOT/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8001 \
        > "$PROJECT_ROOT/logs/fastapi.log" 2>&1 &
    FASTAPI_PID=$!
    echo "$FASTAPI_PID" > "$PROJECT_ROOT/logs/fastapi.pid"

    sleep 3
    if kill -0 "$FASTAPI_PID" 2>/dev/null; then
        info "FastAPI 已启动: PID=$FASTAPI_PID 端口=8001"
    else
        err "FastAPI 启动失败，查看日志: $PROJECT_ROOT/logs/fastapi.log"
        exit 1
    fi
}

# ── 构建前端 ────────────────────────────────────────────
build_frontend() {
    step "构建前端"

    if [ -f "$FRONTEND_DIR/dist/index.html" ]; then
        info "前端 dist 已存在，跳过构建（如需重新构建请删除 dist/）"
        return
    fi

    cd "$FRONTEND_DIR"
    info "安装 npm 依赖..."
    npm install --silent

    info "构建生产版本..."
    npm run build

    if [ ! -f "$FRONTEND_DIR/dist/index.html" ]; then
        err "前端构建失败"
        exit 1
    fi
    info "前端构建完成"
    cd "$PROJECT_ROOT"
}

# ── 启动前端开发服务器 ──────────────────────────────────
start_frontend() {
    step "启动前端开发服务器"

    if [ -f "$PROJECT_ROOT/logs/frontend.pid" ] && kill -0 "$(cat "$PROJECT_ROOT/logs/frontend.pid")" 2>/dev/null; then
        info "前端开发服务器已在运行"
        return
    fi

    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        info "安装前端依赖..."
        cd "$FRONTEND_DIR" && npm install --silent
        cd "$PROJECT_ROOT"
    fi

    info "启动 Vite 开发服务器 (:3000)..."
    cd "$FRONTEND_DIR"
    nohup npm run dev > "$PROJECT_ROOT/logs/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" > "$PROJECT_ROOT/logs/frontend.pid"
    cd "$PROJECT_ROOT"

    sleep 3
    if kill -0 "$FRONTEND_PID" 2>/dev/null; then
        info "前端已启动: PID=$FRONTEND_PID 端口=3000"
    else
        err "前端启动失败，查看日志: $PROJECT_ROOT/logs/frontend.log"
        exit 1
    fi
}

# ── 启动调度器 ──────────────────────────────────────────
start_scheduler() {
    step "启动定时任务调度器"

    cd "$SCHEDULER_DIR"

    # 确保 scheduler/.env 的 SUPER_AGENT_URL 指向本地
    if grep -q "host.docker.internal" "$SCHEDULER_DIR/.env" 2>/dev/null; then
        info "调度器将通过 host.docker.internal 连接本地 FastAPI"
    fi

    docker compose up -d --build

    info "调度器已启动 (celery-beat + celery-worker)"
    cd "$PROJECT_ROOT"
}

# ── 启动 Nginx 前端服务 ─────────────────────────────────
start_nginx() {
    step "启动 Nginx 前端服务"

    # 如果前端 dist 存在，用 nginx 容器提供
    if [ -d "$FRONTEND_DIR/dist" ]; then
        docker stop lucid-nginx 2>/dev/null || true
        docker rm lucid-nginx 2>/dev/null || true

        docker run -d \
            --name lucid-nginx \
            --add-host=host.docker.internal:host-gateway \
            -p 3001:3001 \
            -v "$FRONTEND_DIR/dist:/usr/share/nginx/html:ro" \
            -v "$PROJECT_ROOT/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
            nginx:alpine

        info "Nginx 前端服务已启动: http://localhost:3001"
    else
        warn "未找到前端构建产物，跳过 Nginx。运行: cd frontend/super-agent-chatui && npm run build"
    fi
}

# ── 状态查看 ────────────────────────────────────────────
show_status() {
    step "服务状态"

    echo ""
    echo "  ── 基础设施 ──"
    for svc in lucid-mysql lucid-redis lucid-elasticsearch lucid-minio; do
        if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
            printf "  ${GREEN}●${NC} %-20s 运行中\n" "$svc"
        else
            printf "  ${RED}○${NC} %-20s 未运行\n" "$svc"
        fi
    done

    echo ""
    echo "  ── 应用服务 ──"
    if docker ps --format '{{.Names}}' | grep -q '^lucid-fastapi$'; then
        printf "  ${GREEN}●${NC} %-20s 运行中  (Docker)\n" "lucid-fastapi"
    elif [ -f "$PROJECT_ROOT/logs/fastapi.pid" ] && kill -0 "$(cat "$PROJECT_ROOT/logs/fastapi.pid")" 2>/dev/null; then
        printf "  ${GREEN}●${NC} %-20s 运行中  (本地, PID=%s)\n" "lucid-fastapi" "$(cat "$PROJECT_ROOT/logs/fastapi.pid")"
    else
        printf "  ${RED}○${NC} %-20s 未运行\n" "lucid-fastapi"
    fi

    for svc in lucid-scheduler-beat lucid-scheduler-worker; do
        if docker ps --format '{{.Names}}' | grep -q "^${svc}$"; then
            printf "  ${GREEN}●${NC} %-20s 运行中\n" "$svc"
        else
            printf "  ${RED}○${NC} %-20s 未运行\n" "$svc"
        fi
    done

    if [ -f "$PROJECT_ROOT/logs/frontend.pid" ] && kill -0 "$(cat "$PROJECT_ROOT/logs/frontend.pid")" 2>/dev/null; then
        printf "  ${GREEN}●${NC} %-20s 运行中  (本地, PID=%s)\n" "frontend" "$(cat "$PROJECT_ROOT/logs/frontend.pid")"
    else
        printf "  ${RED}○${NC} %-20s 未运行\n" "frontend"
    fi

    echo ""
    echo "  ── 访问地址 ──"
    echo "  前端页面:    http://localhost:3000"
    echo "  API 文档:    http://localhost:8001/bx/api/docs"
    echo "  MinIO 控制台: http://localhost:9003"
    echo ""
}

# ── 停止所有服务 ────────────────────────────────────────
stop_all() {
    step "停止所有服务"

    # 停止前端开发服务器
    if [ -f "$PROJECT_ROOT/logs/frontend.pid" ]; then
        local fpid
        fpid=$(cat "$PROJECT_ROOT/logs/frontend.pid")
        if kill -0 "$fpid" 2>/dev/null; then
            kill "$fpid" 2>/dev/null || true
            info "已停止前端 (PID=$fpid)"
        fi
        rm -f "$PROJECT_ROOT/logs/frontend.pid"
    fi

    # 停止本地 FastAPI
    if [ -f "$PROJECT_ROOT/logs/fastapi.pid" ]; then
        local pid
        pid=$(cat "$PROJECT_ROOT/logs/fastapi.pid")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            info "已停止 FastAPI (PID=$pid)"
        fi
        rm -f "$PROJECT_ROOT/logs/fastapi.pid"
    fi

    # 停止调度器
    cd "$SCHEDULER_DIR" && docker compose down 2>/dev/null || true
    cd "$PROJECT_ROOT"

    # 停止基础设施
    docker compose down 2>/dev/null || true

    info "所有服务已停止"
}

# ── 主流程 ──────────────────────────────────────────────
main() {
    echo ""
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║        Super-Agent 一键部署              ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo ""

    mkdir -p "$PROJECT_ROOT/logs"

    check_prerequisites
    setup_env
    start_infra
    start_fastapi
    start_scheduler
    start_frontend
    show_status

    info "部署完成！"
    echo ""
    info "查看日志:"
    echo "  FastAPI:  tail -f $PROJECT_ROOT/logs/fastapi.log"
    echo "  前端:     tail -f $PROJECT_ROOT/logs/frontend.log"
    echo "  调度器:   docker logs -f lucid-scheduler-worker"
    echo ""
    info "停止所有服务: $0 --stop"
}

# ── 入口 ────────────────────────────────────────────────
case "${1:-}" in
    --help|-h) usage ;;
    --status)  show_status ;;
    --stop)    stop_all ;;
    *)         main ;;
esac