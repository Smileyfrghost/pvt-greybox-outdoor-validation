# 户外 PV/T 灰箱建模复现仓库

本仓库提供水冷光伏/光热实验的数据解析、质量检查、早期时钟诊断、探索性整日基线与天气工作簿审计。早期代码与最终论文的冻结灰箱验证采用不同协议，区别见[方法与证据说明](docs/METHODS_AND_EVIDENCE.md)。

数据解析覆盖九个实验日的温度/辐照度及电量记录、300 和 500 mL/min 按日设定流量。原始实验记录、完整文献 PDF、申请材料和私有工作日志不随代码发布。

## 当前能做什么

- 从原始记录重建温度与辐照度数据集；
- 修复记录仪计时器复位导致的时间轴中断；
- 保留原始温度通道，`T_inlet_C` 是早期字段名，不代表已确认的集热器入口实测温度；
- 进行以整日为单位的留一日验证；
- 用 JSON 和 Markdown 保存 QC 与局限性。

## 当前不能声称什么

- 没有出口水温，不能声称实测热功率或热效率；
- 流量是按日设定值，不是连续实测量；
- 三月记录仪没有环境温度和风速；
- 早期时钟重建属于带假设的诊断，不能替代后来论文的分段仿射对齐；
- 旧 HIL、PINN、节水和优化控制结果不属于本仓库首版证据。

安装、运行和目录说明见英文版 [README.md](README.md)。

## 文件入口

| 用途 | 文件 |
|---|---|
| 温度和辐照度解析 | `scripts/build_experimental_dataset.py` |
| 电量解析 | `scripts/build_electrical_dataset.py` |
| 早期时钟与偏移诊断 | `analysis/diagnose_electrothermal_alignment.py` |
| 分任务 Persistence / Static OLS / ARX 比较 | `analysis/fit_panel_temperature_models.py`（兼容入口）、`analysis/baseline_comparison.py` |
| 天气工作簿覆盖率与辐照变化检查 | `analysis/audit_irradiance_campaign.py` |
| 命令与目录 | [复现指南](docs/REPRODUCIBILITY.md)、[仓库地图](docs/REPOSITORY_MAP.md) |

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python analysis/audit_irradiance_campaign.py data/raw/irradiance results/irradiance_audit
```

天气脚本预期一分钟观测，瞬时辐照 W/m2，累计辐照 MJ/m2，日照时 h；`.xlsx` 使用 `openpyxl`，旧 `.xls` 另需 `xlrd`。它不确定仪表朝向，不把天气站读数自动转换成板面辐照。最终论文以实测板中心 T1 为目标，水箱温度和格点环境气温按代理输入解释。

基线默认60s；使用旧`elapsed_s`须显式加`--allow-legacy-clock`，仅作为探索诊断。新版在缺测、质量失败、事件分段与长缺口处断开历史；一步、固定时域、整段递推和静态估计分开评分，保留不稳定输出而不裁剪，不再给混合任务总排名。使用规范见[基线比较说明](docs/BASELINE_COMPARISON.md)，后期冻结模型仍属独立协议。
