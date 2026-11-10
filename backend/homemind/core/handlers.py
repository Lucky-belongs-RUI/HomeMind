"""全局异常处理：把业务异常与未捕获异常统一成一致的错误响应体。

注册之后，服务层只需 `raise NotFoundError(...)`，
**API 层不需要再写任何 try/except 做转译**——这是分层的意义：
服务层表达"发生了什么"，HTTP 状态码由基础设施决定。

三类异常各有归宿：

| 异常 | 处理方式 | 客户端看到 |
| --- | --- | --- |
| `AppError` 子类 | 按异常自带的 http_status 与 code 返回 | `{detail, code}` |
| `RequestValidationError` | 提取首个字段错误为可读文案 | `{detail, code, errors}` |
| 其它未捕获异常 | 记录完整堆栈，只返回通用文案 | `{detail, code}` |
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from homemind.core.exceptions import AppError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器（在创建 FastAPI 实例之后调用）。"""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """业务异常：按异常自带的 http_status 与 code 返回。

        4xx 属于预期内的业务结果（记 info），5xx 才是需要关注的问题（记 error）。
        """
        log = logger.info if exc.http_status < 500 else logger.error
        log(
            "业务异常 %s %s -> %s(%s): %s",
            request.method,
            request.url.path,
            exc.http_status,
            exc.code,
            exc.message,
        )
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """请求体校验失败：给出可读文案，同时保留逐字段明细。

        默认实现返回 `detail: [...]`（数组），前端直接展示会很难看；
        这里把首个错误拼成一句人话，同时保留原始 errors 供调试。
        """
        errors = jsonable_encoder(exc.errors())
        first = errors[0] if errors else {}
        field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
        message = first.get("msg", "请求参数校验失败")
        detail = f"{field}: {message}" if field else message
        logger.info("参数校验失败 %s %s: %s", request.method, request.url.path, detail)
        return JSONResponse(
            status_code=422,
            content={"detail": detail, "code": "validation_error", "errors": errors},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        """未捕获异常：记录完整堆栈，但只向客户端返回通用文案。

        注意不要把 `str(exc)` 返回给客户端——那会把内部实现细节（表名、路径、
        第三方库版本）暴露出去。
        """
        logger.exception("未处理异常 %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "服务内部错误", "code": "internal_error"},
        )
