#!/usr/bin/env bash
set -e

NAME="novelforge"
PORT=${PORT:-8000}

usage() {
    echo "用法: $0 {up|down|restart}"
    echo ""
    echo "  up      构建并启动容器"
    echo "  down    停止并删除容器"
    echo "  restart 重新构建并启动"
    exit 1
}

cmd=${1:-up}

case "$cmd" in
    up)
        echo "==> 构建镜像 $NAME ..."
        docker build -t "$NAME" .

        echo "==> 启动容器 $NAME (端口 $PORT) ..."
        [ -f novelforge.db ] || touch novelforge.db
        docker run -d \
            --name "$NAME" \
            -p "$PORT:8000" \
            -v "$(pwd)/novelforge.db:/app/novelforge.db" \
            -v "$(pwd)/.env:/app/.env" \
            --restart unless-stopped \
            "$NAME"

        echo "==> 容器已启动，访问 http://127.0.0.1:$PORT"
        ;;
    down)
        echo "==> 停止并删除容器 $NAME ..."
        docker stop "$NAME" 2>/dev/null || true
        docker rm "$NAME" 2>/dev/null || true
        echo "==> 清理镜像 $NAME ..."
        docker rmi "$NAME" 2>/dev/null || true
        echo "==> 已清理"
        ;;
    restart)
        "$0" down
        "$0" up
        ;;
    *)
        usage
        ;;
esac
