# 安装

## 要求

- Python ≥ 3.10
- 推荐用**独立虚拟环境**(venv / conda),避免与其它行情库(如 mootdx)的依赖冲突。

## pip

```bash
pip install probar                # 核心:东方财富(pb.dc) + 通达信(pb.tdx),通达信协议纯标准库实现
pip install "probar[ths]"         # 实验性:同花顺 / 问财(pb.ths,反爬 best-effort)
pip install "probar[playground]"  # 本地接口可视化测试台
```

## conda(推荐隔离)

```bash
conda create -n probar python=3.12 -y
conda activate probar
pip install "probar[playground]"
```

!!! warning "依赖隔离"
    probar 需要较新的 `httpx`(≥0.27)。若你的环境里装了要求 `httpx<0.26` 的库(如 `mootdx`),
    两者无法共存,请给 probar 用单独的环境。

## 验证

```python
import probar as pb
print(pb.__version__)
pb.capabilities()        # 查看三源能力矩阵
```
