# 澄川智慧供水运营平台 Demo

基于供排水信息化竞品调研成果制作的可运行原型。项目采用 FastAPI，首轮聚焦“运营总览 + DMA 异常处置”最小业务闭环。

## 本机运行

```powershell
python -m uvicorn app.main:app --reload --port 8000
```

打开 <http://127.0.0.1:8000>。

## 回归测试

```powershell
python -m pytest
```

每轮范围、验收口径和回归清单记录在 `docs/iterations/`。
