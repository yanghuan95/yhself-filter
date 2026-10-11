# yhself-filter

只维护根目录的 `selfdirect.list` 和 `special.list`。推送到 `main` 后，GitHub Actions 自动生成、校验并提交五个平台的分流规则集；PR 只验证并提供构建产物。

## 按平台订阅

下面每个平台均提供两个独立规则集。点击链接可获取 Raw 地址；不要把其他平台的文件混用，也不要把源文件当作跨平台订阅。

| 平台 | selfdirect | special | 引用方式 |
| --- | --- | --- | --- |
| Quantumult X / QX | [selfdirect.list](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/quantumult-x/selfdirect.list) | [special.list](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/quantumult-x/special.list) | `[filter_remote]`，文件自带 `direct` |
| Loon | [selfdirect.list](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/loon/selfdirect.list) | [special.list](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/loon/special.list) | `[Remote Rule]`，绑定 `policy=DIRECT` |
| Shadowrocket / 小火箭 | [selfdirect.list](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/shadowrocket/selfdirect.list) | [special.list](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/shadowrocket/special.list) | `[Rule]` 中以 `RULE-SET` 绑定 `DIRECT` |
| mihomo / Clash Meta | [selfdirect.yaml](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/mihomo/selfdirect.yaml) | [special.yaml](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/mihomo/special.yaml) | `rule-providers`，`behavior: classical`、`format: yaml` |
| sing-box | [selfdirect.srs](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/sing-box/selfdirect.srs) / [JSON](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/sing-box/selfdirect.json) | [special.srs](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/sing-box/special.srs) / [JSON](https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/sing-box/special.json) | `route.rule_set` + `route.rules`，绑定直连 outbound |

以下都是需要合并进现有配置的片段，不是完整客户端配置。规则应放在兜底规则之前；客户端也必须使用规则模式。

### Quantumult X

```ini
[filter_remote]
https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/quantumult-x/special.list, tag=yh-special, force-policy=direct, enabled=true
https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/quantumult-x/selfdirect.list, tag=yh-selfdirect, force-policy=direct, enabled=true
```

### Loon

```ini
[Remote Rule]
https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/loon/special.list,policy=DIRECT,enabled=true
https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/loon/selfdirect.list,policy=DIRECT,enabled=true
```

### Shadowrocket

```ini
[Rule]
RULE-SET,https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/shadowrocket/special.list,DIRECT
RULE-SET,https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/shadowrocket/selfdirect.list,DIRECT
```

### mihomo

```yaml
rule-providers:
  yh-special:
    type: http
    behavior: classical
    format: yaml
    url: https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/mihomo/special.yaml
    path: ./rule-providers/yh-special.yaml
    interval: 86400
  yh-selfdirect:
    type: http
    behavior: classical
    format: yaml
    url: https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/mihomo/selfdirect.yaml
    path: ./rule-providers/yh-selfdirect.yaml
    interval: 86400

rules:
  - RULE-SET,yh-special,DIRECT
  - RULE-SET,yh-selfdirect,DIRECT
  # 后面保留现有规则和 MATCH 兜底规则。
```

### sing-box

规则集使用 v2 格式，适用于 sing-box 1.10+；下面的路由片段采用 1.11+ 的 `action` 写法。将 `direct` 替换成现有配置里直连 outbound 的 tag，或添加 `{"type":"direct","tag":"direct"}`。

```json
{
  "route": {
    "rule_set": [
      {
        "type": "remote",
        "tag": "yh-special",
        "format": "binary",
        "url": "https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/sing-box/special.srs",
        "update_interval": "1d"
      },
      {
        "type": "remote",
        "tag": "yh-selfdirect",
        "format": "binary",
        "url": "https://raw.githubusercontent.com/yanghuan95/yhself-filter/main/rules/sing-box/selfdirect.srs",
        "update_interval": "1d"
      }
    ],
    "rules": [
      {
        "rule_set": ["yh-special", "yh-selfdirect"],
        "action": "route",
        "outbound": "direct"
      }
    ]
  }
}
```

使用 JSON 时，把地址后缀改为 `.json`，并把 `format` 改为 `source`。rule-set 本身不携带路由策略，必须同时添加 `route.rules`。

## 源规则格式

两个源文件当前都是直连列表，支持以下等价类型；大小写、逗号周围空格不影响解析。

| 类型 | 含义 | 示例 |
| --- | --- | --- |
| `DOMAIN` / `HOST` | 精确域名 | `DOMAIN,tracker.example.com,DIRECT` |
| `DOMAIN-SUFFIX` / `HOST-SUFFIX` | 域名及其子域名 | `HOST-SUFFIX,example.com,direct` |
| `DOMAIN-KEYWORD` / `HOST-KEYWORD` | 域名关键词 | `DOMAIN-KEYWORD,example,DIRECT` |

第三列可省略，默认 `DIRECT`。支持空行以及以 `#`、`//`、`;` 开头的整行注释；不支持行尾注释。重复规则去重并保留首次出现的顺序，不合并两份列表，也不删除被更宽后缀覆盖的规则。

非法域名、额外字段、未知类型或非 `DIRECT` 策略会报出文件名及行号，并停止生成，保留之前的产物。IP、GEOIP、正则、逻辑规则等暂不转换，避免各平台语义差异导致错误路由。需要增加这些类型时，应同步扩展转换器和校验。

## 工作流与本地生成

修改任一源列表、转换器、测试或工作流后，推送到 `main` 会自动构建。也可在 Actions 中手动运行 **Build platform rules**。只有 `main` 会自动提交产物，其他分支手动运行和 PR 只验证并上传 artifact。机器人只提交 `rules/` 和旧版生成文件，因此不会触发递归构建。

编译器固定为 sing-box `1.13.21`，下载按官方 release 的 SHA-256 校验。两个源文件先全部验证，再编译两个 SRS；全部成功后才覆盖生成文件。若推送期间上游改变导致提交冲突，工作流会失败而不会强行覆盖上游；最新一次源文件推送会触发新的构建。

本地需 Python 3 和 sing-box：

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_rules.py
# 编译器不在 PATH 时：
python3 scripts/build_rules.py --sing-box /path/to/sing-box
```

测试涵盖格式转换、规则完整性、输入错误、失败时保留旧产物，以及真实 SRS 编译/反编译和重复构建一致性。真实编译测试在找不到 sing-box 时跳过；可用 `SING_BOX_BIN=/path/to/sing-box` 指定编译器，CI 会执行该测试。

为兼容已有订阅，根目录的 `selfdirect.json`、`selfdirect.srs`、`selfClashDirect.list` 继续自动更新。`selfClashDirect.list` 是携带 `DIRECT` 的旧式规则片段，不用于 mihomo `rule-providers`；新订阅请使用上表对应平台路径。不要手动修改生成文件。

## 格式参考

- [Quantumult X 官方配置](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)及[规则样例](https://github.com/crossutility/Quantumult-X/blob/master/filter.snippet)
- [Loon 官方配置](https://github.com/Loon0x00/LoonExampleConfig/blob/master/example.conf)及[规则样例](https://github.com/Loon0x00/LoonExampleConfig/blob/master/Rule/ExampleRule.list)
- [mihomo 规则集格式](https://wiki.metacubex.one/config/rule-providers/content/)
- [sing-box 源格式](https://sing-box.sagernet.org/configuration/rule-set/source-format/)及[无策略规则](https://sing-box.sagernet.org/configuration/rule-set/headless-rule/)
