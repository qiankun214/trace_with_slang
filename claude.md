# 编码规范

1. 禁止编写单个超过100行的巨型函数
2. 禁止过度try，可以让错误直接爆出
3. 所有函数必须标注输入的类型和输出类型，必须提供def下文档
4. 有聚合在一起共同语义的变量需要打包成的dataclass
5. 使用loguru打印log信息，便于后续debug

# 文档要求

- doc/ref.md : 技术参考文件，描述包括算法说明，实现流程等
- doc/structure.md : 一页纸说明文件，说明整体架构（一级函数如何组织成功能）和一级函数的输入/输出（带类型）和功能
- doc/readme.md : 暴露的API和使用方法等使用信息
- doc/types.md : 记录所有自定义的类型，另外需要标记功能
- doc/flow1_design_spec.md : 流程①（filelist 解析）行为规格

# Skill规划

- gen-sv-test：用于生成SystemVerilog测试数据
- pyslang：对python库pyslang的认知，有新发现或更新需要写入其中
- trace_with_slang：对本库的认知，如何使用本项目以及开发本项目需要的信息，范例，过程记录等

# 目录构成

- src：原始代码
- test：SystemVerilog测试文件
- tests：pytest单元测试
- ref：参考代码，禁止抄袭，不作为已经实现的功能
- ref_tests：参考代码，禁止使用，不作为已经实现的测试

# python环境

使用 .venv虚拟环境

# agent规范

- 禁止虚构不存在API，有不清楚的可以自行探索/搜索web/询问用户
- 使用plan时，使用中文描述plan，并必须标注需要修改的内容
- 除非用户要求，禁止修改无关代码，基于最小修改考虑