# Fuzz Testing — Samples for Manual Checking

_Generated 2026-10-16 09:51. Companion to [sections_report.md](sections_report.md)._

## A3 — 15 random usage repositories with strong signals

_Seeded random pick from the sampled usage repositories with a technique phrase in ≥1 **test** code file (topped up with the usage repositories with most technique code files if fewer). Evidence only, not a classification._

| Repository | Stars | Language | Tech Test Files | Tech Non-test Files | Hits | Example files | Description |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [huangsam/hotspot](https://github.com/huangsam/hotspot) | 32 | Go | 1 | 0 | 12 | `core/algo/score_test.go` | Agent layer for Git and tech debt 🧠 |
| [catabozan/p3_syscall_server](https://github.com/catabozan/p3_syscall_server) | 0 | C | 6 | 2 | 17 | `sqlite-src-3510100/test/dbfuzz.c`<br>`sqlite-src-3510100/test/dbfuzz2.c`<br>`sqlite-src-3510100/test/fuzzcheck.c`<br>`sqlite-src-3510100/test/optfuzz.c` | — |
| [humbleguidant/HospitalApp](https://github.com/humbleguidant/HospitalApp) | 1 | Python | 1 | 0 | 1 | `DatabaseBackend/flask/opensourceintegration/Lib/site-packages/numpy/core/tests/test_mem_overlap.py` | This is a hospital app created in Apache Cordova and Flask (Python web framework). It includes a chat channel for patients, doctors, and ad… |
| [brianhhuynh38/CSC481-581-GameEngine](https://github.com/brianhhuynh38/CSC481-581-GameEngine) | 2 | C++ | 12 | 1 | 348 | `Libs/libzmq-mt-4_3_5/tests/test_bind_curve_fuzzer.cpp`<br>`Libs/libzmq-mt-4_3_5/tests/test_bind_fuzzer.cpp`<br>`Libs/libzmq-mt-4_3_5/tests/test_bind_null_fuzzer.cpp`<br>`Libs/libzmq-mt-4_3_5/tests/test_bind_stream_fuzzer.cpp` | Repository for the game engine running on SDL2 made for the mixed CSC 481/581 class |
| [acuicultor/RadioactiveKernel_Pantah](https://github.com/acuicultor/RadioactiveKernel_Pantah) | 21 | C | 1 | 6 | 33 | `tools/testing/selftests/kvm/lib/sparsebit.c`<br>`crypto/testmgr.c`<br>`drivers/hv/hv_debugfs.c`<br>`google-modules/wlan/bcmdhd/bcm4389/include/bcmutils.h` | Radioactive kernel for Pixel7 and Pixel7pro (Panther and Cheetah) |
| [ChelseaLiao/AR-Textbook-Hololens2-MRTK3](https://github.com/ChelseaLiao/AR-Textbook-Hololens2-MRTK3) | 0 | C# | 1 | 0 | 2 | `Library/PackageCache/org.mixedrealitytoolkit.spatialmanipulation@7e88bb47473f/Tests/Runtime/ObjectManipulatorTests.cs` | AR learning system, loading materials like articles, pictures and videos online |
| [CPHFOOD/PanelCheck](https://github.com/CPHFOOD/PanelCheck) | 3 | Python | 2 | 0 | 2 | `PanelCheck.app/Contents/Resources/lib/python2.7/numpy/core/tests/test_mem_overlap.py`<br>`PanelCheck.app/Contents/Resources/lib/python2.7/scipy/linalg/tests/test_matfuncs.py` | Standalone for statistical and visual analysis of sensory panel data |
| [clerkma/texlive-mobile](https://github.com/clerkma/texlive-mobile) | 42 | C | 1 | 3 | 34 | `texlive/utils/asymptote/cudareflect/tinyexr/test/unit/tester.cc`<br>`texlive/libs/graphite2/graphite2-src/src/inc/Machine.h`<br>`texlive/libs/icu/icu-src/source/common/rbbinode.cpp`<br>`texlive/libs/icu/icu-src/source/i18n/regexcmp.cpp` | TeX Live for Android/iOS |
| [gridcorestudio/chronovault](https://github.com/gridcorestudio/chronovault) | 0 | Rust | 9 | 81 | 269 | `.cargo/git/checkouts/anchor-50c4b9c8b5e0501f/e6d7daf/tests/cfo/deps/openbook-dex/dex/src/instruction.rs`<br>`.cargo/git/checkouts/anchor-50c4b9c8b5e0501f/e6d7daf/tests/cfo/deps/swap/deps/serum-dex/dex/src/instruction.rs`<br>`.cargo/git/checkouts/anchor-50c4b9c8b5e0501f/e6d7daf/tests/swap/deps/openbook-dex/dex/src/instruction.rs`<br>`.cargo/git/checkouts/anchor-abe899040bbade94/e6d7daf/tests/cfo/deps/openbook-dex/dex/src/instruction.rs` | Decentralized time-locked execution protocol for Solana |
| [COMP-523-Team-D/PhysicsSimulation](https://github.com/COMP-523-Team-D/PhysicsSimulation) | 1 | JavaScript | 1 | 4 | 12 | `frontend/public/phetsims/scenery/tests/qunit/js/from-fuzzer.js`<br>`frontend/public/phetsims/joist/js/Sim.js`<br>`frontend/public/phetsims/perennial/js/listContinuousTests.js`<br>`frontend/public/phetsims/phetmarks/js/phetmarks.js` | — |
| [openshift/insights-runtime-extractor](https://github.com/openshift/insights-runtime-extractor) | 2 | Go | 3 | 8 | 51 | `extractor/vendor/regex-automata/tests/fuzz/dense.rs`<br>`extractor/vendor/regex-automata/tests/fuzz/sparse.rs`<br>`extractor/vendor/regex/tests/fuzz/mod.rs`<br>`exporter/vendor/github.com/fxamacker/cbor/v2/doc.go` | Gather runtime information for the OpenShift Insights Operator |
| [AerospaceVillage/avBadge_2024](https://github.com/AerospaceVillage/avBadge_2024) | 120 | C | 3 | 25 | 156 | `software/winglet-boot/include/test/fuzz.h`<br>`software/winglet-boot/test/fuzz/cmd_fuzz.c`<br>`software/winglet-kernel/tools/testing/selftests/kvm/lib/sparsebit.c`<br>`software/winglet-boot/arch/sandbox/cpu/os.c` | Aerospace Village Badge 2024 |
| [pbatard/uefi-md5sum](https://github.com/pbatard/uefi-md5sum) | 29 | C | 1 | 0 | 42 | `tests/run_tests.sh` | MD5 checksum validation for UEFI |
| [webmproject/libwebp](https://github.com/webmproject/libwebp) | 2,398 | C | 4 | 3 | 17 | `tests/fuzzer/advanced_api_fuzzer.cc`<br>`tests/fuzzer/imageio_fuzzer.cc`<br>`tests/fuzzer/mux_demux_api_fuzzer.cc`<br>`tests/fuzzer/oss-fuzz/build.sh` | Mirror only. Please do not send pull requests. See https://chromium.googlesource.com/webm/libwebp/+/HEAD/CONTRIBUTING.md. |
| [shekhawat2/android_kernel_xiaomi_peridot](https://github.com/shekhawat2/android_kernel_xiaomi_peridot) | 0 | C | 1 | 10 | 46 | `tools/testing/selftests/kvm/lib/sparsebit.c`<br>`crypto/testmgr.c`<br>`drivers/hv/hv_debugfs.c`<br>`include/linux/hyperv.h` | — |

## A6 — 10 random repositories per domain (manual verification)

_Seeded random sample from repositories matched on metadata. 'Matched' = the text that triggered the domain. Mark each as correct / incorrect to estimate precision._

### Web Api

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [stephenzhang0713/go-zero](https://github.com/stephenzhang0713/go-zero) | go-zero is a web and rpc framework written in Go. It's born to ensure the stability of the busy sites with resilient de… | `http`, `microservice`, `microservices` | README | distributed_systems |  |
| [skhuang/stvisual](https://github.com/skhuang/stvisual) | — | `cors`, `http`, `https` | README | — |  |
| [wemake-services/wemake-frontend-styleguide](https://github.com/wemake-services/wemake-frontend-styleguide) | Set of the strictest linters for your next frontend app | `frontend`, `frontend`, `vue` | description/topics | — |  |
| [lihaoyi/SprayWebSockets](https://github.com/lihaoyi/SprayWebSockets) | An implementation of a websocket server on top of spray.io | `websocket`, `http`, `rest`, `websocket` | description/topics | — |  |
| [plugveg/stock-merch-ugs](https://github.com/plugveg/stock-merch-ugs) | — | `backend`, `frontend`, `react` | README | database |  |
| [aws/capability-insights-for-aws](https://github.com/aws/capability-insights-for-aws) | Deploy a regional availability dashboard into your own AWS account, powered by data from AWS Capabilities By Region. | `backend`, `endpoint`, `endpoints`, `rest` | README | — |  |
| [wemake-services/nuxt-babel](https://github.com/wemake-services/nuxt-babel) | Use normal .babelrc file with your Nuxt app | `vue` | description/topics | — |  |
| [protobufjs/protobuf.js](https://github.com/protobufjs/protobuf.js) | High-performance Protocol Buffers for JavaScript and TypeScript. Conformant through Edition 2026, and unusually versati… | `backend`, `http`, `websocket` | README | — |  |
| [lacausecrypto/mcp-wallfacer](https://github.com/lacausecrypto/mcp-wallfacer) | Runtime testing harness for MCP servers: fuzz tools, validate schemas, run YAML invariants and multi-step sequences, sh… | `HTTP`, `http` | description/topics | database, embedded_iot, machine_learning, security_crypto |  |
| [marcuxyz/flask-vuejs](https://github.com/marcuxyz/flask-vuejs) | Connect Flask application with VueJS | `Flask`, `flask`, `flask`, `flask` | description/topics | — |  |

### Security Crypto

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [midas-lex-verus-experiment-forks/sequoia-pgp--sequoia](https://github.com/midas-lex-verus-experiment-forks/sequoia-pgp--sequoia) | VL experiment mirror for non-GitHub upstream | `certificates`, `cryptographic`, `cryptography`, `security` | README | — |  |
| [varungor365/autofuzzer](https://github.com/varungor365/autofuzzer) | Coverage-guided fuzzing framework for authorized vulnerability research and defensive software testing. | `vulnerability`, `security`, `vulnerability`, `buffer overflow` | description/topics | — |  |
| [thrykol/gcp_auth](https://github.com/thrykol/gcp_auth) | Minimal authentication library for Google Cloud Platform (GCP) | `authentication`, `authentication`, `private key` | description/topics | — |  |
| [F0rbidden-Equation/Spectra](https://github.com/F0rbidden-Equation/Spectra) | Spectra is an offensive security framework combining fuzzing, reverse engineering, and exploit management | `security`, `reverse engineering`, `exploit`, `buffer overflow` | description/topics | database, web_api |  |
| [nicolasarnedo99/rareskills-security1](https://github.com/nicolasarnedo99/rareskills-security1) | — | `exploit`, `exploited`, `exploiting`, `exploits` | README | — |  |
| [bhaskix/bhaskix](https://github.com/bhaskix/bhaskix) | — | `cryptography`, `injection`, `privilege escalation`, `security` | README | embedded_iot, operating_systems |  |
| [chesteralan/react-auditor](https://github.com/chesteralan/react-auditor) | A blazing-fast Rust CLI to scan JS/TS/React code for best practices, quality, and security issues. | `security`, `security` | description/topics | web_api |  |
| [Lovsan/RambaZamba](https://github.com/Lovsan/RambaZamba) | collection of networking tools. | `certificate`, `encryption`, `security`, `ssl` | README | — |  |
| [ithxforyou/setup-java](https://github.com/ithxforyou/setup-java) | Set up your GitHub Actions workflow with a specific version of Java | `authentication`, `private key`, `security` | README | — |  |
| [groundlens-dev/groundlens](https://github.com/groundlens-dev/groundlens) | GroundLens is an execution verification runtime for AI systems and agents. It turns observable AI execution into determ… | `security`, `tls` | description/topics | machine_learning |  |

### Database

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [Sylverfox96/firstApp](https://github.com/Sylverfox96/firstApp) | — | `database`, `postgresql`, `query`, `transactional` | README | security_crypto |  |
| [bbgoyalbb/Retail-App](https://github.com/bbgoyalbb/Retail-App) | An Web App for Retail Management | `database`, `mongodb`, `normalization` | README | web_api |  |
| [apache/opendal](https://github.com/apache/opendal) | Apache OpenDAL: One Layer, All Storage. | `databases`, `mongodb`, `postgresql`, `sqlite` | README | — |  |
| [apollosolutions/example-custom-check](https://github.com/apollosolutions/example-custom-check) | Repository with a sample applications for implementing a GraphOS Schema Check webhook integration | `Schema`, `schema` | description/topics | — |  |
| [Mohamedbg23/fleet-mcp](https://github.com/Mohamedbg23/fleet-mcp) | One MCP tool that runs a command on every server at once. 212-token schema vs 1631-9801 for comparable SSH MCP servers;… | `schema`, `schema`, `schemas` | description/topics | — |  |
| [ydb-platform/ydb-go-sdk](https://github.com/ydb-platform/ydb-go-sdk) | Pure Go native and database/sql driver for YDB | `database`, `sql`, `database`, `sql` | description/topics | distributed_systems |  |
| [J-C-Lab/Synapse](https://github.com/J-C-Lab/Synapse) | — | `orm`, `schema`, `schemas` | README | security_crypto, web_api |  |
| [ssandy33/regress](https://github.com/ssandy33/regress) | — | `database`, `schemas`, `sqlite` | README | finance, operating_systems, web_api |  |
| [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB) | A super fast Graph Database uses GraphBLAS under the hood for its sparse adjacency matrix graph representation. Our goa… | `Database`, `database`, `database`, `database` | description/topics | machine_learning, scientific_computing |  |
| [GrandShow/FerretDB](https://github.com/GrandShow/FerretDB) | A truly Open Source MongoDB alternative | `MongoDB`, `database`, `databases`, `mongodb` | description/topics | — |  |

### Compiler Pl

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [dertin/code-system-graph](https://github.com/dertin/code-system-graph) | Open-source, local code intelligence and dependency graph for cross-repository impact analysis. Map APIs, events, schem… | `static analysis`, `compiler`, `static analysis` | description/topics | database, distributed_systems, web_api |  |
| [dcSpark/cddl-codegen](https://github.com/dcSpark/cddl-codegen) | Codegen (de)serialization logic for CBOR automatically from a CDDL specification | `Codegen`, `codegen`, `codegen` | description/topics | — |  |
| [norm-format/norm-rust](https://github.com/norm-format/norm-rust) | A Rust parser and encoder for the NORM data format | `parser`, `parser` | description/topics | — |  |
| [raymyers/ralph-cc-go](https://github.com/raymyers/ralph-cc-go) | Prototype C compiler in Go made with OpenHands coding agent | `compiler`, `compiler` | description/topics | — |  |
| [4fuu/noc.h](https://github.com/4fuu/noc.h) | — | `ast`, `compiler`, `parser` | README | — |  |
| [superlambchops/open62541](https://github.com/superlambchops/open62541) | Open source implementation of OPC UA (OPC Unified Architecture) aka IEC 62541 licensed under Mozilla Public License v2.0 | `code generation`, `compiler`, `compilers` | README | operating_systems |  |
| [laiyoufafa/third_party_spirv-tools](https://github.com/laiyoufafa/third_party_spirv-tools) | — | `compiler`, `compilers`, `parser` | README | — |  |
| [lurk-lab/lurk-beta](https://github.com/lurk-lab/lurk-beta) | Lurk is a Turing-complete programming language for recursive zk-SNARKs. This is the prior, elliptic curve based variant… | `programming language`, `compiler`, `programming language`, `programming languages` | description/topics | security_crypto |  |
| [rafaelmgr12/jingo](https://github.com/rafaelmgr12/jingo) | Jingo is a high-performance JSON parser and encoder for Go. | `parser`, `abstract syntax tree`, `ast`, `parser` | description/topics | — |  |
| [wsollers/fuzzing-experiments](https://github.com/wsollers/fuzzing-experiments) | Fuzz testing experiments for C/C++ with CodeQL AST-guided fuzzing, OpenGrep security analysis, coverage reporting, and … | `AST`, `ast`, `llvm`, `parser` | description/topics | security_crypto |  |

### Operating Systems

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [ernestojeda/edgex-go](https://github.com/ernestojeda/edgex-go) | EdgeX Golang Services Monorepo | `container`, `containers`, `scheduler` | README | — |  |
| [compsec-snu/razzer](https://github.com/compsec-snu/razzer) | A Kernel fuzzer focusing on race bugs | `Kernel`, `kernel`, `scheduler` | description/topics | — |  |
| [black-hat-pikachu/envoy](https://github.com/black-hat-pikachu/envoy) | Cloud-native high-performance edge/middle/service proxy | `container`, `thread`, `threading` | README | — |  |
| [pilotspace/moon](https://github.com/pilotspace/moon) | moon - memory boosting for Spaceship | `concurrency`, `container`, `kernel`, `thread` | README | database |  |
| [hpenne/basic-snmp-agent](https://github.com/hpenne/basic-snmp-agent) | — | `thread`, `threaded`, `threads` | README | — |  |
| [me-diru/tremor-runtime](https://github.com/me-diru/tremor-runtime) | Main Tremor Project Rust Codebase | `container`, `operating systems`, `thread` | README | — |  |
| [dominikb1888/bobs_new](https://github.com/dominikb1888/bobs_new) | Course Page for the course Digital Business Skills (Module: General Business Administration and Accounting) at DIT.  | `operating system`, `operating systems`, `virtualization` | README | finance |  |
| [GSI-HPC/slurm-singularity-exec](https://github.com/GSI-HPC/slurm-singularity-exec) | The Singularity SPANK plugin provides the users with an interface to launch an application within a Linux container. | `container`, `container` | description/topics | — |  |
| [triton/triton](https://github.com/triton/triton) | Triton Operating System | `Operating System`, `operating system` | description/topics | — |  |
| [astrid-runtime/astrid](https://github.com/astrid-runtime/astrid) | Astrid is a portable, capability-secure operating system for composable software. | `operating system`, `kernel`, `operating system` | description/topics | machine_learning, security_crypto, web_api |  |

### Finance

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [0x1d00ffff/0xbtc-discord-price-bot](https://github.com/0x1d00ffff/0xbtc-discord-price-bot) | bot to monitor/post price etc to the 0xbtc discord server | `exchange`, `exchanges`, `trading` | README | — |  |
| [PatrickMockridge/DarkWow](https://github.com/PatrickMockridge/DarkWow) | Private and Anonymous Orchestration, Governance and DeFi with Object Capability Primitives | `DeFi`, `blockchain`, `cryptocurrency`, `defi` | description/topics | security_crypto |  |
| [Menjay7/Hunty-contract](https://github.com/Menjay7/Hunty-contract) | — | `blockchain`, `marketing`, `smart contracts` | README | — |  |
| [sherlock-audit/2024-10-mento-update-judging](https://github.com/sherlock-audit/2024-10-mento-update-judging) | — | `exchange`, `exchanges`, `trading` | README | — |  |
| [noosi21/codex-solidity](https://github.com/noosi21/codex-solidity) | Codex Solidity - Smart Contract Audit CLI with 34 skills, GPT-5.4 xhigh reasoning, symbolic execution, fuzzing (Echidna… | `Smart Contract`, `defi`, `risk`, `risks` | description/topics | compiler_pl, security_crypto |  |
| [dev-protocol/template-repos-ts-sol](https://github.com/dev-protocol/template-repos-ts-sol) | Template repository for using TypeScript and Solidity | `smart contracts` | description/topics | — |  |
| [euler-xyz/reward-streams](https://github.com/euler-xyz/reward-streams) | Reward Streams allows permissionless rewards distribution of multiple tokens in staking and staking-free manner | `blockchain`, `exchange`, `smart contract` | README | — |  |
| [cryptocatgirl/ubiquity-dollar](https://github.com/cryptocatgirl/ubiquity-dollar) | Repository created by GitHub Project Operator | `exchange`, `smart contract`, `smart contracts` | README | — |  |
| [lbryio/lbrycrd](https://github.com/lbryio/lbrycrd) | The blockchain that provides the digital content namespace for the LBRY protocol | `blockchain`, `blockchain`, `cryptocurrency`, `blockchain` | description/topics | — |  |
| [JSTONE1111/nearcore](https://github.com/JSTONE1111/nearcore) | Reference client for NEAR Protocol | `blockchain`, `blockchains`, `smart contracts` | README | — |  |

### Machine Learning

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [firecrawl/firecrawl](https://github.com/firecrawl/firecrawl) | Supercharge your AI agents with data from the web and beyond. Building the library for superintelligence. 🔥 | `llm`, `llm` | description/topics | — |  |
| [astrid-runtime/astrid](https://github.com/astrid-runtime/astrid) | Astrid is a portable, capability-secure operating system for composable software. | `llm`, `llm` | description/topics | operating_systems, security_crypto, web_api |  |
| [torchvideo/torchvideo](https://github.com/torchvideo/torchvideo) | :movie_camera: Datasets, transforms and samplers for video in PyTorch | `PyTorch`, `machine learning`, `pytorch`, `computer vision` | description/topics | — |  |
| [Dongdongshe/neuzz](https://github.com/Dongdongshe/neuzz) | neural network assisted fuzzer | `neural network`, `keras`, `tensorflow` | description/topics | — |  |
| [bact/pitloom](https://github.com/bact/pitloom) | SBOM generation for Python & AI projects. Native Hatchling build-hook. Extract metadata from GGUF, ONNX, and PyTorch mo… | `PyTorch`, `keras`, `pytorch` | description/topics | — |  |
| [fang407/TeamTree](https://github.com/fang407/TeamTree) | TeamTree working here | `classifications`, `llm`, `ml model`, `regression` | README | security_crypto, web_api |  |
| [kandluis/yelp-star-reviews](https://github.com/kandluis/yelp-star-reviews) | Yelp Review Predictions Using Graph Structures and Deep Learning | `Deep Learning` | description/topics | — |  |
| [davidspek/pipelines](https://github.com/davidspek/pipelines) | Machine Learning Pipelines for Kubeflow | `Machine Learning`, `machine learning` | description/topics | — |  |
| [wandb/wandb](https://github.com/wandb/wandb) | The AI developer platform. Use Weights & Biases to train and fine-tune models, and manage models from experimentation t… | `deep learning`, `keras`, `machine learning`, `pytorch` | description/topics | — |  |
| [sebastienrousseau/bankstatementparser](https://github.com/sebastienrousseau/bankstatementparser) | Parse bank statements (CAMT, PAIN.001, MT940, MT942, OFX/QFX, BAI2, CSV, and PDF) into unified Transactions. Treasury a… | `LLM`, `llm`, `llms` | description/topics | compiler_pl, database, finance, security_crypto, web_api |  |

### Embedded Iot

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [aibudaevv/sip-exporter](https://github.com/aibudaevv/sip-exporter) | Open-source eBPF sensor for IPv4/UDP SIP and correlated RTP/RTCP metrics in Prometheus and Grafana. Support: https://gi… | `sensor`, `real-time`, `sensor` | description/topics | web_api |  |
| [nuwaLab/wingmuzz](https://github.com/nuwaLab/wingmuzz) | WingMuzz is a two-dimensional fuzzing schedule framework for IoT protocols. It enhances blackbox fuzzing with the power… | `IoT`, `iot` | description/topics | — |  |
| [tinyrange/renvo_emu](https://github.com/tinyrange/renvo_emu) | Renvo Emulator (remu): deterministic microcontroller emulation and firmware qualification in Rust | `microcontroller`, `firmware`, `bootloader`, `firmware` | description/topics | compiler_pl, operating_systems |  |
| [GunnarMorrigan/mqrstt](https://github.com/GunnarMorrigan/mqrstt) | Pure rust async MQTTv5 client | `iot` | description/topics | — |  |
| [George-Yanni/FuzzMatryoshka](https://github.com/George-Yanni/FuzzMatryoshka) | FuzzMatryoshka is a Radamsa-based fuzzing framework designed to stress-test and harden the Matryoshka firmware update p… | `firmware`, `firmware` | description/topics | compiler_pl |  |
| [groovenauts/SmartShoppingNavigator](https://github.com/groovenauts/SmartShoppingNavigator) | Smart Shopping Cart Demonstration applications to show integration of GCP Cloud IoT Core and Machine Leaning Engine | `IoT`, `iot`, `raspberry` | description/topics | — |  |
| [PelionIoT/java-coap](https://github.com/PelionIoT/java-coap) | CoAP Java library | `iot`, `embedded` | description/topics | — |  |
| [SoulSolistice/esphome_vitohome](https://github.com/SoulSolistice/esphome_vitohome) | An ESPHome external component for Viessmann heating controllers over the Optolink interface. | `arduino`, `firmware`, `real-time`, `sensor` | README | — |  |
| [simpleiot/simpleiot](https://github.com/simpleiot/simpleiot) | Simple IoT cloud/edge application/framework | `IoT`, `iot`, `iot`, `iot` | description/topics | web_api |  |
| [prusa3d/Prusa-Firmware-Buddy](https://github.com/prusa3d/Prusa-Firmware-Buddy) | Firmware for the Original Prusa MINI, Original Prusa MK4, Original Prusa XL and Prusa CORE One 3D printers by Prusa Res… | `Firmware`, `firmware`, `bootloader`, `bootloaders` | description/topics | — |  |

### Distributed Systems

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [Blackcoin-Dev/Blackcoin](https://github.com/Blackcoin-Dev/Blackcoin) | Quantum Upgrade to Blackcoin | `consensus`, `rpc`, `rpcs` | README | — |  |
| [salosh/nudnik](https://github.com/salosh/nudnik) | Nudnik - Infrastructure Fuzzing | `grpc`, `load balancing`, `grpc` | description/topics | web_api |  |
| [stephenzhang0713/go-zero](https://github.com/stephenzhang0713/go-zero) | go-zero is a web and rpc framework written in Go. It's born to ensure the stability of the busy sites with resilient de… | `rpc`, `load balancing`, `rpc`, `rpcs` | description/topics | web_api |  |
| [paraloom-labs/paraloom-core](https://github.com/paraloom-labs/paraloom-core) | Open privacy Layer 2 for Solana. Groth16 zk-SNARKs, BFT cohort, ~10 ms verification on commodity hardware. Pre-mainnet. | `consensus`, `dht`, `rpc` | README | finance, security_crypto, web_api |  |
| [Kava-Labs/tendermint](https://github.com/Kava-Labs/tendermint) | ⟁ Tendermint Core (BFT Consensus) in Go | `Consensus`, `consensus`, `replication`, `rpc` | description/topics | — |  |
| [hanzoai/kv](https://github.com/hanzoai/kv) | Ultra-fast key-value store with Redis API compatibility | `replication`, `rpc`, `sharding` | README | database |  |
| [VanL/simplebroker](https://github.com/VanL/simplebroker) | A lightweight, no-configuration message broker/queue for cli tools | `distributed`, `message queue`, `rabbitmq`, `replication` | README | database |  |
| [pmehnert/distributed-string-sorting](https://github.com/pmehnert/distributed-string-sorting) | Master's Thesis on Scalable Distributed String Sorting Algorithms | `Distributed`, `distributed`, `distributed` | description/topics | — |  |
| [sub0xdai/testudo-raas](https://github.com/sub0xdai/testudo-raas) | A containerized rust microservice that isolates mathematical risk logic from network I/O through a   stateless gRPC int… | `gRPC`, `grpc` | description/topics | finance, operating_systems, web_api |  |
| [oxen-io/lokinet](https://github.com/oxen-io/lokinet) | Lokinet is an anonymous, decentralized and IP based overlay network for the internet. | `dht` | description/topics | — |  |

### Scientific Computing

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [QSOLKCB/igm](https://github.com/QSOLKCB/igm) | Research-grade simulation infrastructure for immunoglobulin M (IgM) structural hypotheses, with strict separation betwe… | `simulation`, `computational`, `numerical`, `simulation` | description/topics | database |  |
| [Reference-LAPACK/lapack](https://github.com/Reference-LAPACK/lapack) | LAPACK development repository | `eigenvalues`, `linear algebra`, `matrix`, `linear algebra` | description/topics | — |  |
| [cctbx/cctbx_project](https://github.com/cctbx/cctbx_project) | Computational Crystallography Toolbox | `Computational`, `computational` | description/topics | — |  |
| [stp/stp](https://github.com/stp/stp) | Simple Theorem Prover, an efficient SMT solver for bitvectors, floating-point and arrays. | `solver`, `solver`, `solver` | description/topics | security_crypto, web_api |  |
| [hgascon/pulsar](https://github.com/hgascon/pulsar) | Protocol Learning and Stateful Fuzzing | `simulation`, `simulation` | description/topics | security_crypto |  |
| [CGCL-codes/HistFuzz](https://github.com/CGCL-codes/HistFuzz) | A practical fuzzing tool for SMT solvers | `solvers`, `solvers` | description/topics | — |  |
| [duerrsimon/colab-db.github.io](https://github.com/duerrsimon/colab-db.github.io) | Repository of Jupyter Notebooks on Colab, Binder and Huggingface for Bio, Chemistry and Physics | `Physics` | description/topics | — |  |
| [jpgomesr/netchaos](https://github.com/jpgomesr/netchaos) | Deterministic net.Conn/net.Listener fault injection for Go — the testing/synctest philosophy applied to the network lay… | `simulation`, `simulation` | description/topics | distributed_systems, security_crypto, web_api |  |
| [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB) | A super fast Graph Database uses GraphBLAS under the hood for its sparse adjacency matrix graph representation. Our goa… | `matrix`, `computational`, `linear algebra`, `matrix` | description/topics | database, machine_learning |  |
| [matrix-org/matrix-authentication-service](https://github.com/matrix-org/matrix-authentication-service) | OAuth2.0 + OpenID Provider for Matrix Homeservers | `Matrix`, `matrix` | description/topics | — |  |

### Autonomous Robotics

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [Pascal-0x90/FuzzingEngine](https://github.com/Pascal-0x90/FuzzingEngine) | Fuzzing Engine for ASU 2020 Drone Fuzzing Capstone | `Drone` | description/topics | — |  |
| [VarZ-96/agentic-chaos-crash-test](https://github.com/VarZ-96/agentic-chaos-crash-test) | An adversarial fuzzing and resiliency evaluation platform for autonomous LLM agents in production environments. | `autonomous`, `autonomous` | description/topics | database, machine_learning, web_api |  |
| [yechun1/rosdistro](https://github.com/yechun1/rosdistro) | This repo maintains a lists of repositories for each ROS distribution | `ROS`, `mappings`, `ros` | description/topics | — |  |
| [chilumine/ghosting_apis.py](https://github.com/chilumine/ghosting_apis.py) | Phan tich dong API hay - Comprehensive API security testing tool that performs attack surface mapping, parameter fuzzin… | `mapping`, `mapping` | description/topics | database, operating_systems, security_crypto, web_api |  |
| [Shest-Programmistov/Smart-Pots](https://github.com/Shest-Programmistov/Smart-Pots) | IoT project implementing remote care for a potted plant through sensors and robotics, which monitor its state. | `robotics`, `robotics` | description/topics | embedded_iot, web_api |  |
| [emocat/VioHawk](https://github.com/emocat/VioHawk) | VioHawk: Detecting Traffic Violations of Autonomous Driving Systems through Criticality-guided Simulation Testing | `Autonomous`, `autonomous` | description/topics | scientific_computing |  |
| [emberdragonc/ember-staking](https://github.com/emberdragonc/ember-staking) | 🐉 Multi-token staking contract for the Ember ecosystem. Stake EMBER, earn fees from autonomous builds. | `autonomous`, `autonomous` | description/topics | — |  |

## T9 — 50 random relevant commits from 2026 (manual check: agent-written?)

| Repository | Date | Agent-marked | Message (first 300 chars) | Agent? (manual) |
| --- | --- | --- | --- | --- |
| [ariacomputecompany/fozzy](https://github.com/ariacomputecompany/fozzy/commit/9d92fca3da564d358d4f0ee818bfe2a8ac76b96b) | 2026-02-20 |  | Expand fuzz targets, schema/validate, map attribution, and policy UX |  |
| [s3s-project/s3s](https://github.com/s3s-project/s3s/commit/dad24543a50f1ff0c182a1216040c327273cf3b4) | 2026-08-27 |  | ci(fuzz): add PR fmt/lint gate (#731) * ci(fuzz): add PR fmt/lint gate Add a fuzz-lint job that runs 'just -f fuzz/justfile ci-check' (formatting check + clippy with the fuzzing cfg) on pull_request when fuzz/** changes. The fuzz/ tree is a separate cargo workspace not covered by the root ci.yml, so |  |
| [astera-hq/Astera](https://github.com/astera-hq/Astera/commit/d2e5f125f8cc924a41eeb685e65d26e238cdd8ab) | 2026-05-28 | yes | fix(ci): register credit-score fuzz test target explicitly Wire up credit_score fuzz tests as a named integration target to keep CI test target resolution deterministic. Co-authored-by: Cursor <cursoragent@cursor.com> |  |
| [sunderee/new-arp-scan](https://github.com/sunderee/new-arp-scan/commit/5358c70bb9ebf4e090798ead5a06e5cb5feb38e4) | 2026-08-29 |  | test(fuzz): add a cargo-fuzz target for the Ethernet/ARP decode chain 'fuzz/fuzz_targets/parse_ethernet_arp.rs' drives the crate's only untrusted-input boundary through the public reply parser: Ethernet header, IEEE 802.1Q tag stack, RFC 1042 LLC/SNAP, RFC 826 ARP. 'fuzz/' is its own workspace, so t |  |
| [Soren-999/testing](https://github.com/Soren-999/testing/commit/bf8ac6a25b376548aabfc5d62d8cff5f361c2a8c) | 2026-06-19 |  | Revert "[Fuzzing] Remove testing/buildbot/chromium.fuzz.json." This reverts commit c1806d72f5475197a23005a185f3a8b58aed2eeb. Reason for revert: broke some libfuzzer builds Failure Link: https://ci.chromium.org/ui/p/chromium/builders/try/linux-libfuzzer-high-end-asan-rel/68/overview Original change's |  |
| [Dicklesworthstone/asupersync](https://github.com/Dicklesworthstone/asupersync/commit/67cb2113f4a2318a9aa0a4afd611a3ce0287b99f) | 2026-04-28 |  | [br-asupersync-wjai3e] add auth AAD construction fuzz target |  |
| [group-5-cs412a/fuzz-libsixel](https://github.com/group-5-cs412a/fuzz-libsixel/commit/92bf3c0cada52b32cea94232cea8d97eb6a06dfc) | 2026-05-14 |  | Merge origin/feat/faster-and-deeper-greybox into feat/qemu Prioritizing greybox fuzzing functionality: - Integrated complex 8-byte control header in harness.c - Added SEED_PROFILE, BROAD_LOADER, and TRUEVISION_PATCH options to Makefile - Consolidated launch_fuzzer.sh to support both native and QEMU  |  |
| [wilsonzlin/aero](https://github.com/wilsonzlin/aero/commit/960360040976cb3c89596837046eeaca2ab26028) | 2026-01-11 |  | docs(fuzz): mention ATAPI in storage fuzz targets |  |
| [Zero-kernel/Nilix](https://github.com/Zero-kernel/Nilix/commit/3ab6c572c3962174796b9b4189695405ccbbe4ca) | 2026-08-04 |  | test(fuzz): update fuzz runner and stress test scripts Update deterministic KCOV test runner and validation scripts to coexist with new syzkaller infrastructure. Changes: - Clarify fuzz_runner.c is deterministic E2E, not mutation-driven - Update test scripts to reference new fuzzing documentation -  |  |
| [realm-labs/starclock](https://github.com/realm-labs/starclock/commit/67a912fe61f85aaa8f270dda64102e35146351d0) | 2026-07-22 |  | test(agent): G02-P5-B1 retain hardening fuzz corpus |  |
| [yaksetig/tarsier](https://github.com/yaksetig/tarsier/commit/a2db4f25bc22340bb22f2f99c78f25d229351967) | 2026-02-19 | yes | Add fuzz testing for the DSL parser Set up cargo-fuzz with a fuzz_parse target that exercises tarsier_dsl::parse on arbitrary byte strings, seeded with 5 example .trs protocols. Run with: cargo +nightly fuzz run fuzz_parse Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> |  |
| [szymonwilczek/lota](https://github.com/szymonwilczek/lota/commit/ce6b308a787e0611a59cf2be1aafa3d32f9b35fb) | 2026-02-15 |  | store: add fuzzing for client ID, hardware ID, and certificates - FuzzValidateClientID: fuzz path traversal protection with 7 seeds including NUL bytes, slashes, dot-dot sequences - FuzzParseHardwareID: fuzz hex decoding with round-trip validation - FuzzParseAIKCertificate: fuzz DER X.509 parsing (u |  |
| [Dicklesworthstone/asupersync](https://github.com/Dicklesworthstone/asupersync/commit/72fa480efc3e44788628b2ae23a14fe26a7d0bb4) | 2026-05-09 |  | [br-asupersync-esidyb] Keep MySQL result-set fuzz target compiling |  |
| [NguyenQuan121321/FinnApiGo](https://github.com/NguyenQuan121321/FinnApiGo/commit/ae46cceac2d23fb5ffa0bf6d48aa758fdab50c2a) | 2026-08-28 |  | test(security): fuzz targets for JWT parsing, TOTP validation, recovery-code consumption [T2] |  |
| [webrtc-rs/rtc](https://github.com/webrtc-rs/rtc/commit/5f596f10af233a84b29f0d66ff39bc38c55ffe3a) | 2026-02-20 |  | Add rtc-dtls fuzz test (#48) * add fuzz test for rtc-dtls * add sanity check for unmarshal functions Fixed possible panic related to buf size found by fuzz test. |  |
| [Ionablokchain/Iona-protocol](https://github.com/Ionablokchain/Iona-protocol/commit/7cc644ca82f05b29e26dd1709786915fa14a7323) | 2026-06-14 |  | Update block_header.rs feat(fuzz): production‑ready fuzzing harness for block deserialization - Enforce input size limit (4 MiB) to prevent OOM in fuzzer. - Add safe JSON deserialization with recursion limit (depth 128). - Suppress error logging (only debug) to reduce noise. - Use 'std::hint::black_ |  |
| [rush86999/atom](https://github.com/rush86999/atom/commit/664b0c0a61aa28529641d783a6ce8d2f09b30bfc) | 2026-03-24 | yes | docs(239): create phase plan for API Fuzzing Infrastructure Created 5 plans for Phase 239: API Fuzzing Infrastructure Wave 1: - 239-01: FuzzingOrchestrator service and crash deduplication (FUZZ-01, FUZZ-06) Wave 2: - 239-02: Auth endpoint fuzzing harnesses (FUZZ-03) - 239-03: Agent execution and can |  |
| [freebatteryfactory/Macroonz](https://github.com/freebatteryfactory/Macroonz/commit/210cd4033404b146b04d57e97f3cc9eb6f8d68b6) | 2026-08-27 | yes | feat(fuzz): introduce 'fuzz-frida' feature for enhanced coverage with LibAFL and Frida Add a new 'fuzz-frida' feature to the harness, enabling the integration of the LibAFL and Frida mechanisms for coverage-guided fuzzing. This feature is optional and does not interfere with existing configurations. |  |
| [EMBA-support-repos/RTOSploit](https://github.com/EMBA-support-repos/RTOSploit/commit/a059af6f3a942f16ff24d6dd2b22dd3d84355dc6) | 2026-03-21 |  | docs: reorder features to match workflow — analyze, CVE, exploit, rehost, fuzz, report Reorder feature descriptions across README and SVG banner to reflect the natural assessment workflow: 1. Static Analysis 2. CVE Correlation 3. Vulnerability Assessment & Exploit Generation 4. Firmware Rehosting 5. |  |
| [OssaBellator/UCOF](https://github.com/OssaBellator/UCOF/commit/79d87e12ea2840e9c3917efc6df3803e10ec2c91) | 2026-08-02 |  | Smoke source mixed fuzz target |  |
| [BakeLens/crust](https://github.com/BakeLens/crust/commit/f562413c6e5c988d59238a336d9e1ceb42725248) | 2026-03-04 |  | fix: fail-closed on unparseable shell commands to prevent rule bypass Commands that fail AST parsing are now flagged as evasive instead of passed through. The rule engine cannot analyze what it cannot parse, so blocking is the safe default against malformed-syntax bypass attempts. Updates tests to r |  |
| [Oichkatzelesfrettschen/silksurf](https://github.com/Oichkatzelesfrettschen/silksurf/commit/144c054ee6a0aa18fcfb0936e3bc288b5db74f43) | 2026-01-29 | yes | Integrate AFL++ fuzzing infrastructure (Task #31) Added comprehensive AFL++ fuzzing support for security testing of HTML and CSS parsers with persistent mode harnesses. CMakeLists.txt: - Added ENABLE_FUZZING option to enable AFL++ instrumentation - Auto-detect afl-clang-fast compiler - Added custom  |  |
| [k-arrows/clang-assert-tests](https://github.com/k-arrows/clang-assert-tests/commit/890cc38022b74024173ab2eb5dc5d94f8abc9251) | 2026-05-21 |  | fuzzing: add files for clang fuzzing with tree-crasher |  |
| [KoteshMurugan/smite](https://github.com/KoteshMurugan/smite/commit/8cdb6d17f430037eee36b77974815a5f638ca122) | 2026-01-09 |  | Implement basic LND fuzz target The fuzz target does the Noise protocol handshake and exchanges init messages with LND, then sends raw fuzzer data over the connection. The LND fuzz target was originally written by Niklas Gögge and several key framework components are adapted from Fuzzamoto (https:// |  |
| [branover/hexgraph](https://github.com/branover/hexgraph/commit/4387fcd84093cc363573626032fc3f503b49f0ad) | 2026-06-01 |  | Merge pull request #49 from branover/build/fuzz-phase0 feat: coverage-guided fuzzing + crash dedup/minimize/exploitability (Phase 0) |  |
| [PelicanPlatform/classad](https://github.com/PelicanPlatform/classad/commit/7efdf7550ffabac4900a4373ff9c95b09f10dc6d) | 2026-06-30 | yes | classad: unknown function is error without evaluating arguments evaluateFunctionCall evaluated all arguments before dispatching, so an unknown function's arguments were evaluated -- and a cyclic argument (A0 = 0 =!= A((A0))) aborted the whole expression to error instead of the reference's true (the  |  |
| [KooshaPari/Dino](https://github.com/KooshaPari/Dino/commit/b141b8ca84c31c67ecfb8b8b628e45e547da96d9) | 2026-08-20 |  | test(fuzz): add asset pipeline fuzz test target |  |
| [nmaguiar/ntwire](https://github.com/nmaguiar/ntwire/commit/dfa2feeed66eb69b22f615c96edf2095328d559a) | 2026-08-16 |  | feat(server): update dataplane and add socks fuzz tests - Update dataplane implementation and tests - Add fuzz tests for socks package |  |
| [cypherpulse/hermesbridge-poolv1](https://github.com/cypherpulse/hermesbridge-poolv1/commit/fd96d27e55f28f03ea06e50884108a13478585b3) | 2026-05-27 |  | test: fuzz test withdrawal amount limits |  |
| [kramu39/mensari-staking-vault](https://github.com/kramu39/mensari-staking-vault/commit/0a2ca970b810b290b10850b425e1a4988d8eb24e) | 2026-05-18 |  | test: add fuzz tests for reward distribution |  |
| [GaloyMoney/cala](https://github.com/GaloyMoney/cala/commit/5e0391d4e784ff631c8f21f0f7e1bd17e5154d47) | 2026-08-09 |  | test: add cargo-fuzz workspace for cel interpreter and core types (#826) * test: add cargo-fuzz workspace for cel interpreter and core types Three libFuzzer targets covering the library's in-memory attack surface: - cel_compile: CEL compilation of arbitrary strings - cel_evaluate: compilation + eval |  |
| [Diggsey/ijson](https://github.com/Diggsey/ijson/commit/22d911ddf8ecd20fa1edde51b04b156a7dd5e964) | 2026-07-09 |  | Make INumber::from_str preserve exact decimals from_str previously ran every float-shaped string through parse::<f64>(), so "0.1" became the f64 approximation (and spilled to the heap) rather than the exact decimal it denotes — defeating the reason the string constructor exists. It now parses the di |  |
| [maatini/bpmninja](https://github.com/maatini/bpmninja/commit/c1260703553a5f891393761722dd5a16896b9dcc) | 2026-04-09 |  | feat: add 3 new fuzz targets (token_deserialize, cron_expression, deploy_roundtrip) - fuzz_token_deserialize: Token, ProcessInstance, HistoryEntry, FileReference deserialization - fuzz_cron_expression: croner cron expression parsing and next_occurrence - fuzz_deploy_roundtrip: end-to-end XML → parse |  |
| [Yun131518/HASA](https://github.com/Yun131518/HASA/commit/2ed180a08cf7d1844535eb18dcb0b65bce3b5d05) | 2026-06-21 |  | fix: decodePublicKey missing length check — Jazzer-found bug Jazzer coverage-guided fuzzing (100k runs per target) found ArrayIndexOutOfBoundsException in decodePublicKey() when Base64 payload decodes to an empty or non-33-byte array. BC's decodePoint() reads raw[0] to determine compressed/uncompres |  |
| [Firma-AI/openfirma](https://github.com/Firma-AI/openfirma/commit/d1e917a0b44e893c719f8107bdd1e6b9c76495f1) | 2026-05-13 |  | fix fuzz test |  |
| [OssaBellator/UCOF](https://github.com/OssaBellator/UCOF/commit/e813a927e76ce7e9fb4afd913b921acad1a1bc9a) | 2026-07-31 |  | style: format successor source-history fuzz target |  |
| [Dicklesworthstone/asupersync](https://github.com/Dicklesworthstone/asupersync/commit/05de2b0eb5d6cbb99d58deef7dec44ce87bc8a43) | 2026-05-11 |  | [br-asupersync-lhx6m4.47] Register TLS handshake fuzz target |  |
| [jccontrerasg08-cpu/agent-traffic-intelligence](https://github.com/jccontrerasg08-cpu/agent-traffic-intelligence/commit/9c86f91560b3d36e5cd90db27662034123fae07d) | 2026-08-19 |  | Merge pull request #39 from jccontrerasg08-cpu/test/jsonl-fuzzing test: fuzz JSONL ingestion error boundaries |  |
| [Dicklesworthstone/asupersync](https://github.com/Dicklesworthstone/asupersync/commit/fd3373f6b249ad38e1e9289c00b571cf29036e34) | 2026-05-10 |  | [br-asupersync-lhx6m4.14] Harden oneshot poll-after-await fuzz target |  |
| [Koopa0/yomihon](https://github.com/Koopa0/yomihon/commit/197d81e393c001e342753712e866a333847e3029) | 2026-07-06 |  | Merge pull request #19 from Koopa0/test/diff-fuzz test: add the differential fuzz harness for the judge |  |
| [eugenepentland/guardian-zig](https://github.com/eugenepentland/guardian-zig/commit/91a707542051aaacb4b4055638ccafacaed0e71a) | 2026-08-04 |  | feedback: ward — fuzz-harness allocator hygiene, pub-api rename noise on a file move |  |
| [sanskarpan/http-server](https://github.com/sanskarpan/http-server/commit/10e7b82a1ff757b3de42e9af24398503d041b906) | 2026-05-25 |  | Merge pull request #68 from sanskarpan/track-34-internal-server-fuzz-test-go Track file 34 - internal-server-fuzz-test-go |  |
| [jsonwisdom/receiptos-base](https://github.com/jsonwisdom/receiptos-base/commit/a536d49dca3dd776c4ab714688f36410966b9b47) | 2026-06-29 |  | add deterministic Farcaster manifest fuzz harness |  |
| [3webs-org/spicule](https://github.com/3webs-org/spicule/commit/06e51e198a18e1539e326e6f1d39f2f6984509c3) | 2026-08-27 |  | Add IPv6 fuzz target |  |
| [architehc/nanochat-rs-ternary](https://github.com/architehc/nanochat-rs-ternary/commit/9cb49abbd31961d9468012284554392a1b08733d) | 2026-02-13 | yes | Implement P2 long-term improvements from Kimi Agent review All 5 P2 items completed: 1. ✅ Property-Based Tests with proptest (mhc-lite) - 6 property tests for mHC doubly stochastic invariants - Tests: N2/N4 mixing matrices always DS for ANY parameters - Tests: Composite gain bounded ≤ 1.0 for any se |  |
| [khanaffan/sqlite-msgpack](https://github.com/khanaffan/sqlite-msgpack/commit/68a68d17ba05863c274dcf64a304428c92fa6b5f) | 2026-04-06 | yes | Update SQLite to 3.51.3 and expand fuzz test coverage - Update SQLite amalgamation from 3.53.0 (unreleased) to 3.51.3 (latest stable release, 2026-03-13) - Expand fuzz_msgpack.c to cover all registered SQL entry points: - Add msgpack_quote, msgpack(), msgpack_to_jsonb - Add 2-arg path variants (vali |  |
| [toriyama237/NoeDB](https://github.com/toriyama237/NoeDB/commit/c12ca6788779c86066b04621444dcef1af241dcb) | 2026-05-21 |  | build(fuzz): cargo-fuzz target for lexer robustness Wire a libFuzzer harness that feeds arbitrary UTF-8 into tokenize(), matching the Week 04 fuzzing deliverable. |  |
| [Deadman-Motive/stxStaking](https://github.com/Deadman-Motive/stxStaking/commit/7aed501e6c2efedb2d5fa848aa1926c7f201f26a) | 2026-05-25 |  | test: fuzz test staking duration limits |  |
| [chesteralan/react-auditor](https://github.com/chesteralan/react-auditor/commit/99051acf15f1194ee395ac2c0e992cbb9c57c2bf) | 2026-07-03 |  | feat: new rules, auto-fix, fuzz harness, testing category - no-array-index-key: separate rule flagging key={index/i/j/idx} - no-state-in-default-props: warn on this.state refs in defaultProps - prefer-fragments: add auto-fix (replaces <div>...</div> with <>...</>) - testing category: no-skipped-test |  |
| [Dicklesworthstone/franken_node](https://github.com/Dicklesworthstone/franken_node/commit/f48fdea7ad98ea521d7333ce19e8c5a1e281fbbf) | 2026-04-20 | yes | feat(security): comprehensive SSRF policy + intent firewall fuzzing - Add structure-aware fuzz target for SSRF prevention system with IPv4 parsing edge cases - Test CIDR range boundary conditions, IP address format bypasses, and allowlist manipulation - Implement custom Arbitrary traits for security |  |

## T9 — Repositories with the most relevant commits

| Repository | Relevant commits |
| --- | --- |
| standardgalactic/chimera | 1,206 |
| FreeRADIUS/freeradius-server | 527 |
| Dicklesworthstone/asupersync | 256 |
| joyguoguo/oss-fuzz-py2 | 164 |
| AurumCoinOrg/AurumCoin | 133 |
| Kino1994/bitcoin-full-history | 132 |
| baba-chain/BabaChain | 124 |
| defenwycke/bitcoin-core-ladder-script | 122 |
| WilliamBrown899RobertLane/gui | 121 |
| edge-smith3tb/namecoin-core | 105 |
