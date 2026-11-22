# 灌区配水核算台

灌区调度员在送水前核对闸令、渠道损耗与斗口的当轮配额，再生成回执草案。工作台可切换干净和脏样例，核算后下载一份带原始行与规则版本的证据。

```sh
docker compose up --build
```

访问 `http://127.0.0.1:18449`，先看尾量调平，再点取水权版本和渠道损耗复核来源。脏样例有交叠权证和分支闸门冲突，回执保持待审。`docker compose exec -T app pytest -q` 运行测试。默认命名卷 `records` 保存归档，宿主变量 `DB_PATH` 可指定 SQLite 文件。宿主运行可先安装 `requirements.txt`，再执行 `uvicorn app.main:app --port 18449`。

- [计算顺序、七个模块与陷阱](docs/DEPTH.md)
- [数据字典](docs/DATA-DICTIONARY.md)
- [接口与证据](docs/API.md)
