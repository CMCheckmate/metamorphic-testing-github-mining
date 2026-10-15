# Property-Based Testing — Samples for Manual Checking

_Generated 2026-10-16 09:50. Companion to [sections_report.md](sections_report.md)._

## A3 — 15 random usage repositories with strong signals

_Seeded random pick from the sampled usage repositories with a technique phrase in ≥1 **test** code file (topped up with the usage repositories with most technique code files if fewer). Evidence only, not a classification._

| Repository | Stars | Language | Tech Test Files | Tech Non-test Files | Hits | Example files | Description |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [superdevvs/Repro_Backend](https://github.com/superdevvs/Repro_Backend) | 0 | PHP | 44 | 0 | 44 | `tests/Feature/AccountLifecycleSafetyGuardsPropertyTest.php`<br>`tests/Feature/AccountStatusTotalityPropertyTest.php`<br>`tests/Feature/AuditedActionLoggingPropertyTest.php`<br>`tests/Feature/BatchSizeBoundTest.php` | Repro Backend folder  |
| [jim-schilling/splurge-vendor-sync](https://github.com/jim-schilling/splurge-vendor-sync) | 1 | Python | 1 | 0 | 5 | `tests/unit/test_property_based.py` | Splurge Vendor Sync Utility |
| [surreal70/diskmon](https://github.com/surreal70/diskmon) | 0 | Python | 4 | 0 | 15 | `tests/test_collector_properties.py`<br>`tests/test_display_properties.py`<br>`tests/test_formatter_properties.py`<br>`tests/test_monitor_properties.py` | Simple diskmon commandline tool in python |
| [jamesgober/query-lang](https://github.com/jamesgober/query-lang) | 0 | Rust | 1 | 0 | 2 | `tests/proptests.rs` | Query-based incremental compilation framework. |
| [emi-dm/SonarQ-Agnostic](https://github.com/emi-dm/SonarQ-Agnostic) | 0 | Python | 3 | 0 | 15 | `backend/tests/pbt/test_connection_validation.py`<br>`backend/tests/pbt/test_issue_validation.py`<br>`backend/tests/unit/test_connections_api.py` | — |
| [GitRusSG/shape-drawing-game](https://github.com/GitRusSG/shape-drawing-game) | 0 | JavaScript | 3 | 0 | 3 | `tests/colorscale.test.js`<br>`tests/persistence.test.js`<br>`tests/shapestore.test.js` | — |
| [Digital-Defiance/express-suite-tools](https://github.com/Digital-Defiance/express-suite-tools) | 0 | TypeScript | 16 | 0 | 20 | `audit/tests/analyzers/coverage-analyzer.test.ts`<br>`audit/tests/analyzers/cross-package-analyzer.test.ts`<br>`audit/tests/analyzers/documentation-analyzer.test.ts`<br>`audit/tests/analyzers/ecies-analyzer.test.ts` | — |
| [kswiatek92/HexCrawl](https://github.com/kswiatek92/HexCrawl) | 0 | Python | 2 | 0 | 4 | `tests/unit/domain/services/test_dungeon_generator.py`<br>`tests/unit/domain/services/test_score_service_properties.py` | Project for learning |
| [silver2dream/ai-workflow-kit](https://github.com/silver2dream/ai-workflow-kit) | 2 | Go | 1 | 0 | 1 | `internal/kickoff/integration_test.go` | AWK is a spec-driven execution system for turning AI coding agents into a governed engineering workflow. |
| [Dicklesworthstone/frankenterm](https://github.com/Dicklesworthstone/frankenterm) | 121 | Rust | 475 | 14 | 583 | `crates/frankenterm-core/tests/proptest_accounts.rs`<br>`crates/frankenterm-core/tests/proptest_adaptive_radix_tree.rs`<br>`crates/frankenterm-core/tests/proptest_aegis_backpressure.rs`<br>`crates/frankenterm-core/tests/proptest_aegis_diagnostics.rs` | Terminal hypervisor for AI agent swarms: real-time pane capture, state-machine pattern detection, and a JSON API for coordinating fleets of… |
| [Avinashbudige/masai_hackaton](https://github.com/Avinashbudige/masai_hackaton) | 0 | Python | 6 | 1 | 35 | `tests/property/__init__.py`<br>`tests/property/test_conflict_detector_properties.py`<br>`tests/property/test_data_model_properties.py`<br>`tests/property/test_network_graph_properties.py` | — |
| [jesseadams/waterwaycleanups.org](https://github.com/jesseadams/waterwaycleanups.org) | 1 | HTML | 6 | 0 | 29 | `tests/e2e/auth/authentication.spec.ts`<br>`tests/e2e/auth/session-management.spec.ts`<br>`tests/e2e/minors/minor-edge-cases.spec.ts`<br>`tests/e2e/minors/minor-management.spec.ts` | — |
| [bbalser/Placebo](https://github.com/bbalser/Placebo) | 15 | Elixir | 1 | 0 | 1 | `test/placebo_test.exs` | — |
| [wyattowalsh/ai-web-feeds](https://github.com/wyattowalsh/ai-web-feeds) | 0 | TypeScript | 8 | 0 | 41 | `tests/tests/packages/ai_web_feeds/test_embeddings.py`<br>`tests/tests/packages/ai_web_feeds/test_recommendations.py`<br>`tests/tests/packages/ai_web_feeds/test_search.py`<br>`tests/tests/packages/ai_web_feeds/unit/test_export.py` | AI/ML web feeds |
| [Saravanabhavan-s/Second-Life-Commerce](https://github.com/Saravanabhavan-s/Second-Life-Commerce) | 0 | Python | 1 | 0 | 3 | `backend/tests/test_properties.py` | — |

## A6 — 10 random repositories per domain (manual verification)

_Seeded random sample from repositories matched on metadata. 'Matched' = the text that triggered the domain. Mark each as correct / incorrect to estimate precision._

### Web Api

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [caasi/dong3](https://github.com/caasi/dong3) | A Claude Code skill that lets you delegate tasks to external OpenAI-compatible chat endpoints. Probe capabilities first… | `endpoints`, `endpoints`, `react` | description/topics | — |  |
| [opd-ai/go-tor](https://github.com/opd-ai/go-tor) | Tor client(not a relay, not an exit) in pure Go. | `endpoint`, `endpoints`, `http` | README | security_crypto |  |
| [navikt/tilbakekreving](https://github.com/navikt/tilbakekreving) | — | `http`, `openapi`, `swagger` | README | — |  |
| [schubydoo/withe](https://github.com/schubydoo/withe) | A dashboard for the Renovate you already run. | `endpoint`, `http`, `https` | README | security_crypto |  |
| [ghostventuresai/ghost_camunda](https://github.com/ghostventuresai/ghost_camunda) | — | `react`, `spring boot`, `web application` | README | distributed_systems |  |
| [krushit1307/CampusConnect](https://github.com/krushit1307/CampusConnect) | — | `backend`, `frontend`, `react` | README | database, security_crypto |  |
| [TimOliver/WebServerKit](https://github.com/TimOliver/WebServerKit) | A fork of the #1 HTTP server for iOS, macOS & tvOS | `HTTP`, `http`, `https`, `web server` | description/topics | operating_systems |  |
| [schubydoo/clauster](https://github.com/schubydoo/clauster) | Your homelab's Claude Code launchpad. Self-hosted web UI that spawns & manages remote-control bridges on a remote host … | `fastapi`, `endpoint`, `fastapi`, `https` | description/topics | — |  |
| [leocavalcante/siler](https://github.com/leocavalcante/siler) | ⚡ Flat-files and plain-old PHP functions rockin'on as a set of general purpose high-level abstractions. | `graphql`, `http`, `websockets`, `graphql` | description/topics | — |  |
| [foundryside-dev/hamlet](https://github.com/foundryside-dev/hamlet) | — | `backend`, `expressed`, `frontend`, `vue` | README | database |  |

### Database

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [nicholas-ruest/lang-graph-rs](https://github.com/nicholas-ruest/lang-graph-rs) | — | `indexing`, `schema`, `sqlite` | README | operating_systems |  |
| [aandresalvarez/athena_client](https://github.com/aandresalvarez/athena_client) | Python SDK for the OHDSI Athena Concepts API | `database`, `indexing`, `postgresql`, `query` | README | — |  |
| [akshithnallaginnela/CodeSahayak](https://github.com/akshithnallaginnela/CodeSahayak) | CodeSahayak - TypeScript project by Akshith Nallaginnela. Built with TypeScript. | `database`, `databases`, `elasticsearch`, `postgresql` | README | security_crypto, web_api |  |
| [joshniemela/KU-courses](https://github.com/joshniemela/KU-courses) | A better version of KU's course catalogue | `database`, `database`, `schema` | description/topics | — |  |
| [eputnam77/FedStyleValidator](https://github.com/eputnam77/FedStyleValidator) | Check Word documents against federal writing, formatting, accessibility, and terminology rules | `database`, `schema`, `sqlite` | README | web_api |  |
| [firebase/firebase-android-sdk](https://github.com/firebase/firebase-android-sdk) | Firebase Android SDK | `database`, `database`, `database` | description/topics | — |  |
| [MaudGautier/pebbledb](https://github.com/MaudGautier/pebbledb) | An implementation of RocksDB (https://github.com/facebook/rocksdb) from scratch in Python | `database`, `key-value store`, `query`, `storage engine` | README | operating_systems |  |
| [LarsArtmann/SQLC-Wizzard](https://github.com/LarsArtmann/SQLC-Wizzard) | An interactive CLI wizard that generates perfect sqlc configurations | `database`, `postgresql`, `schema`, `sql` | README | — |  |
| [GyaanFlow/tds-roe-solver-t12026](https://github.com/GyaanFlow/tds-roe-solver-t12026) | TDS Portal Solver is a production-grade, highly secure, browser-based sandbox environment designed for the automated ex… | `schema`, `schemas`, `sql`, `transaction` | README | machine_learning, scientific_computing, web_api |  |
| [Joao-Pedro-P-Holanda/flask-boilerplate](https://github.com/Joao-Pedro-P-Holanda/flask-boilerplate) | template for simple web applications made with flask, using SQLAlchemy ORM and Flask-migrate | `ORM`, `database`, `schema`, `schemas` | description/topics | web_api |  |

### Security Crypto

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [MoosicBox/MoosicBox](https://github.com/MoosicBox/MoosicBox) | A music app for cows | `authentication`, `security`, `tls` | README | database |  |
| [syan212/CryptoPyX](https://github.com/syan212/CryptoPyX) | A python cryptography package written in Rust for fun. | `cryptography`, `cryptography`, `cryptography` | description/topics | — |  |
| [lpesk/cryptopals](https://github.com/lpesk/cryptopals) | python 3 solutions to the cryptopals challenges: https://cryptopals.com/ | `decryptions`, `encryption`, `encryptions`, `hash functions` | README | — |  |
| [Psychevus/cryptography-suite](https://github.com/Psychevus/cryptography-suite) | A comprehensive cryptography toolkit for secure, scalable applications with advanced encryption and hashing. | `cryptography`, `encryption`, `cryptographic`, `cryptography` | description/topics | — |  |
| [sdldev/dockpal](https://github.com/sdldev/dockpal) | — | `security`, `ssl`, `tls` | README | web_api |  |
| [Danielfoojunwei/Fully-Homormorphic-Encrpytion-Classical-ML-Hintsight-Limited](https://github.com/Danielfoojunwei/Fully-Homormorphic-Encrpytion-Classical-ML-Hintsight-Limited) | — | `authorization`, `cryptographic`, `cryptography`, `decryption` | README | finance, machine_learning |  |
| [simplystated/rs-attenuable-jwt](https://github.com/simplystated/rs-attenuable-jwt) | Attenuable JWT implementation in Rust | `authorization`, `private key`, `public key`, `security` | README | web_api |  |
| [kike-alt/DeWordle](https://github.com/kike-alt/DeWordle) | A decentralized, blockchain-based word-guessing game built on the Stellar ecosystem. It merges the fun and challenge of… | `security` | description/topics | database, finance, web_api |  |
| [akshithnallaginnela/CodeSahayak](https://github.com/akshithnallaginnela/CodeSahayak) | CodeSahayak - TypeScript project by Akshith Nallaginnela. Built with TypeScript. | `authentication`, `injection`, `security` | README | database, web_api |  |
| [schubydoo/withe](https://github.com/schubydoo/withe) | A dashboard for the Renovate you already run. | `authentication`, `certificate`, `certificates`, `security` | README | web_api |  |

### Finance

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [Anastasia-Labs/direct-offer](https://github.com/Anastasia-Labs/direct-offer) | — | `blockchain`, `exchange`, `market`, `smart contract` | README | — |  |
| [Abso1ut3Zer0/nexus](https://github.com/Abso1ut3Zer0/nexus) | High Performance Low-Latency Frameworks | `defi`, `market`, `trading` | README | machine_learning, operating_systems, web_api |  |
| [Solders-Girdles-Org/GPT-Trader](https://github.com/Solders-Girdles-Org/GPT-Trader) | — | `backtesting`, `market`, `risk`, `trading` | README | — |  |
| [LegalQuants/lq-ai](https://github.com/LegalQuants/lq-ai) | Open-source AI for legal teams. Bring your own keys, run it where you want, own your data. | `market`, `marketing`, `risk`, `risks` | README | web_api |  |
| [sacherjj/CasperLabs](https://github.com/sacherjj/CasperLabs) | — | `blockchain`, `smart contract`, `smart contracts` | README | — |  |
| [mainstar123/SN55](https://github.com/mainstar123/SN55) | — | `derivatives`, `exchange`, `markets`, `volatility` | README | — |  |
| [Hug0x0/hyperliquid-asset-catalog](https://github.com/Hug0x0/hyperliquid-asset-catalog) | — | `market`, `markets`, `risk`, `trading` | README | security_crypto |  |
| [solutions-plug/predictIQ](https://github.com/solutions-plug/predictIQ) | PredictIQ Contracts is a comprehensive prediction market platform built on Stellar's Soroban smart contract platform. T… | `market`, `smart contract`, `markets`, `market` | description/topics | embedded_iot |  |
| [AlphaB135/BitQuan](https://github.com/AlphaB135/BitQuan) | A minimal Proof-of-Work blockchain with Dilithium PQC (post-quantum cryptography) and public UTXO ledger - 50+ year qua… | `blockchain`, `blockchain`, `cryptocurrency`, `blockchain` | description/topics | distributed_systems, security_crypto |  |
| [luxfi/threshold](https://github.com/luxfi/threshold) | ▼ LUX multiparty CGGMP21, FROST, LSS protocol and other threshold signature schemes. | `blockchain`, `blockchains`, `defi` | README | security_crypto |  |

### Machine Learning

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [mignon-sussman674r/awesome-python](https://github.com/mignon-sussman674r/awesome-python) | Repository created by GitHub Project Operator | `classification`, `computer vision`, `deep learning`, `keras` | README | compiler_pl, database, operating_systems, security_crypto, web_api |  |
| [agobbifbk/DSIPTS_PTF](https://github.com/agobbifbk/DSIPTS_PTF) | Unified library for timeseries modelling **PTF** | `convolutional`, `deep learning`, `pytorch`, `transformer` | README | — |  |
| [Danielfoojunwei/Fully-Homormorphic-Encrpytion-Classical-ML-Hintsight-Limited](https://github.com/Danielfoojunwei/Fully-Homormorphic-Encrpytion-Classical-ML-Hintsight-Limited) | — | `machine learning`, `ml models`, `regression`, `scikit-learn` | README | finance, security_crypto |  |
| [atharvadevne123/Stock-Market-Intelligence](https://github.com/atharvadevne123/Stock-Market-Intelligence) | A comprehensive open-source stock market intelligence system that combines CEO earnings call sentiment analysis, live m… | `classification`, `nlp`, `transformer` | README | database, finance, web_api |  |
| [ldamoncgberry/awesome-python](https://github.com/ldamoncgberry/awesome-python) | Repository created by GitHub Project Operator | `classification`, `computer vision`, `deep learning`, `keras` | README | compiler_pl, database, operating_systems, security_crypto, web_api |  |
| [nodebox/nodebox](https://github.com/nodebox/nodebox) | Node-based data application for visualization and generative design | `generative`, `generative`, `generative` | description/topics | — |  |
| [kdorling/insulin-response](https://github.com/kdorling/insulin-response) | — | `machine learning`, `ml model`, `model training`, `regression` | README | — |  |
| [Uvacoder/aaa-fastapi-collect](https://github.com/Uvacoder/aaa-fastapi-collect) | — | `classifications`, `keras`, `machine learning`, `ml model` | README | database, security_crypto, web_api |  |
| [JuliaRegistries/General](https://github.com/JuliaRegistries/General) | The official registry of general Julia packages | `generative`, `large language model`, `llm`, `llms` | README | — |  |
| [danieleschmidt/retreival-free-context-compressor](https://github.com/danieleschmidt/retreival-free-context-compressor) | A transformer plug-in that compresses long documents into dense "mega-tokens," enabling 256k-token context without exte… | `transformer`, `large language models`, `llm`, `pytorch` | description/topics | — |  |

### Operating Systems

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [glebec/batching-toposort](https://github.com/glebec/batching-toposort) | Efficiently sort interdependent tasks into a sequence of concurrently-executable batches | `concurrency` | description/topics | — |  |
| [dburkart/vibix](https://github.com/dburkart/vibix) | Can we autonomously vibe code a kernel? Let's find out! | `kernel`, `kernel`, `operating system`, `concurrency` | description/topics | — |  |
| [carby/snakestream](https://github.com/carby/snakestream) | Snakestream lets you create streams, inspired by the Java streams API | `concurrency`, `container`, `thread`, `threaded` | README | — |  |
| [tinaudio/synth-setter](https://github.com/tinaudio/synth-setter) | Synthesizer parameter prediction, sound matching, and preset exploration tools. | `container`, `containers`, `posix` | README | machine_learning |  |
| [ldamoncgberry/awesome-python](https://github.com/ldamoncgberry/awesome-python) | Repository created by GitHub Project Operator | `concurrency`, `scheduler`, `virtualization` | README | compiler_pl, database, machine_learning, security_crypto, web_api |  |
| [broadinstitute/cromwell](https://github.com/broadinstitute/cromwell) | Scientific workflow engine designed for simplicity & scalability. Trivially transition between one off use cases to mas… | `containers` | description/topics | bioinformatics |  |
| [Smmemsscoutrscd/serenity](https://github.com/Smmemsscoutrscd/serenity) | The Serenity Operating System 🐞 | `Operating System`, `file system`, `file systems`, `kernel` | description/topics | security_crypto |  |
| [DnzzL/notara](https://github.com/DnzzL/notara) | Self-hosted Notion alternative. One SQLite file, one container, no cloud. | `container`, `container`, `containers` | description/topics | database, security_crypto, web_api |  |
| [younes-io/booking-manager-api](https://github.com/younes-io/booking-manager-api) | A simple Booking Manager API | `concurrency`, `deadlocks`, `memory management` | README | web_api |  |
| [adewale/testing-best-practices](https://github.com/adewale/testing-best-practices) | A Claude Code skill for enforcing testing best practices: TDD, property-based testing, real objects over mocks, test qu… | `concurrency`, `thread`, `virtualization` | README | database, finance, machine_learning |  |

### Compiler Pl

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [OpenAPITools/openapi-generator](https://github.com/OpenAPITools/openapi-generator) | OpenAPI Generator allows generation of API client libraries (SDK generation), server stubs, documentation and configura… | `code generation`, `codegen`, `compiler` | README | web_api |  |
| [Mkerian10/pluto](https://github.com/Mkerian10/pluto) | — | `ast`, `codegen`, `compiler`, `llvm` | README | database, operating_systems |  |
| [ergoplatform/sigmastate-interpreter](https://github.com/ergoplatform/sigmastate-interpreter) | ErgoScript compiler and ErgoTree Interpreter implementation for Ergo blockchain | `compiler`, `Interpreter`, `compiler`, `interpreter` | description/topics | finance, security_crypto |  |
| [stevenvo780/ST](https://github.com/stevenvo780/ST) | — | `ast`, `interpreter`, `parser`, `type checker` | README | — |  |
| [hedyorg/hedy](https://github.com/hedyorg/hedy) | Hedy is a gradual programming language to teach children programming. Gradual languages use different language levels, … | `programming language`, `programming language` | description/topics | — |  |
| [0xAX/erlang-bookmarks](https://github.com/0xAX/erlang-bookmarks) | All about erlang programming language [powerd by community] | `programming language` | description/topics | — |  |
| [kitarefake/cpython](https://github.com/kitarefake/cpython) | — | `compiler`, `compilers`, `interpreter` | README | — |  |
| [jessealama/thales](https://github.com/jessealama/thales) | TypeScript compiler and JavaScript engine in Lean | `compiler`, `compiler`, `type system` | description/topics | — |  |
| [btq-ag/keelung-compiler](https://github.com/btq-ag/keelung-compiler) | The core optimizing backend for Keelung, responsible for compiling high-level Haskell programs into efficient constrain… | `compiler`, `compiler` | description/topics | scientific_computing, web_api |  |
| [chboishabba/SensibLaw](https://github.com/chboishabba/SensibLaw) | Like coleslaw, it just makes sense. | `compiler`, `parser`, `parsers` | README | database, web_api |  |

### Distributed Systems

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [AlphaB135/BitQuan](https://github.com/AlphaB135/BitQuan) | A minimal Proof-of-Work blockchain with Dilithium PQC (post-quantum cryptography) and public UTXO ledger - 50+ year qua… | `rpc`, `consensus`, `rpc` | description/topics | finance, security_crypto |  |
| [jreuben11/triad](https://github.com/jreuben11/triad) | Rust framework for integrating PostgreSQL, Redis and Kafka | `Kafka`, `distributed`, `grpc`, `kafka` | description/topics | database, web_api |  |
| [oddsdk/ts-odd](https://github.com/oddsdk/ts-odd) | An SDK for building apps with decentralized identity and storage. | `distributed`, `distributed` | description/topics | security_crypto, web_api |  |
| [ghostventuresai/ghost_camunda](https://github.com/ghostventuresai/ghost_camunda) | — | `fault tolerance`, `grpc`, `kafka`, `message queues` | README | web_api |  |
| [CalderKnox/scrapy-extension](https://github.com/CalderKnox/scrapy-extension) | Distributed crawling for Scrapy with pluggable backends + strategy layers (dedup/queue). | `Distributed`, `distributed`, `kafka`, `load balancing` | description/topics | database, operating_systems, security_crypto, web_api |  |
| [dogmatiq/veracity](https://github.com/dogmatiq/veracity) | 🚫 A horizontally-scalable event-sourced Dogma engine. | `grpc`, `partitioning`, `sharding` | README | — |  |
| [Govcraft/agent-uri-rs](https://github.com/Govcraft/agent-uri-rs) | Rust implementation of the Agent URI scheme for topology-independent agent identity and capability-based discovery | `dht`, `distributed`, `replication` | README | security_crypto, web_api |  |
| [habitat-sh/habitat](https://github.com/habitat-sh/habitat) | Modern applications with built-in automation | `distributed`, `distributed` | description/topics | operating_systems |  |
| [raymondtay/jobgraph](https://github.com/raymondtay/jobgraph) | Distributed Workflow Scheduler for Apache Beam jobs | `Distributed`, `distributed` | description/topics | database, operating_systems |  |
| [erewok/raft-hs](https://github.com/erewok/raft-hs) | An implementation of Raft in Haskell | `Raft`, `raft` | description/topics | — |  |

### Scientific Computing

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [QMCPACK/qmcpack](https://github.com/QMCPACK/qmcpack) | Main repository for QMCPACK, an open-source production level many-body ab initio Quantum Monte Carlo code for computing… | `Monte Carlo`, `monte carlo`, `monte carlo` | description/topics | — |  |
| [bakabala27-svg/NAAS-Agentic-Core](https://github.com/bakabala27-svg/NAAS-Agentic-Core) | — | `linear algebra`, `physics`, `simulation` | README | web_api |  |
| [chapel-lang/chapel](https://github.com/chapel-lang/chapel) | a Productive Parallel Programming Language | `scientific computing` | description/topics | compiler_pl, distributed_systems, operating_systems |  |
| [ahmdelbaz28-ux/BAZspark](https://github.com/ahmdelbaz28-ux/BAZspark) | Safety-Critical Fire Alarm Engineering & Digital Twin Platform — NFPA 72-2022 / Vite + React + FastAPI | `computational`, `physics`, `simulation` | README | database, operating_systems, security_crypto, web_api |  |
| [luk036/ginger-rs](https://github.com/luk036/ginger-rs) | 🫚 Polynomial Root-finding Methods (parallelizable) in Rust | `numerical` | description/topics | — |  |
| [D-sorganization/Tools](https://github.com/D-sorganization/Tools) | Engineering and scientific desktop applications: process calculators, signal and data processing, URDF and robotics mod… | `scientific computing`, `signal processing`, `differential equations`, `signal processing` | description/topics | autonomous_robotics |  |
| [ev-br/scipy](https://github.com/ev-br/scipy) | Scipy main repository | `fourier`, `linear algebra`, `numerical`, `solvers` | README | — |  |
| [swe-train/scipy__scipy](https://github.com/swe-train/scipy__scipy) | — | `fourier`, `linear algebra`, `numerical`, `solvers` | README | — |  |
| [Jebel-Quant/linalg](https://github.com/Jebel-Quant/linalg) | Linear algebra utilities for portfolio optimization | `Linear algebra`, `eigenvalue`, `eigenvalues`, `linear algebra` | description/topics | finance |  |
| [luchocarg/hodge-decomposition](https://github.com/luchocarg/hodge-decomposition) | Haskell graph flow decomposition engine using discrete Poisson relaxation and property-based testing | `matrix`, `numerical`, `solver` | README | — |  |

### Embedded Iot

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [aldis-ameriks/plant-lab](https://github.com/aldis-ameriks/plant-lab) | IoT platform for plant monitoring 🌱 | `IoT` | description/topics | — |  |
| [zhongwencool/emqx](https://github.com/zhongwencool/emqx) | An Open-Source, Cloud-Native, Distributed MQTT Message Broker for IoT. | `IoT`, `iot`, `real-time` | description/topics | distributed_systems, security_crypto |  |
| [C360Studio/semstreams](https://github.com/C360Studio/semstreams) | A Go framework for building streaming pipelines that produce live semantic knowledge graphs. Designed for environments … | `iot`, `real-time`, `sensor` | README | web_api |  |
| [Amperstrand/microfips](https://github.com/Amperstrand/microfips) | Minimal FIPS leaf node on STM32F469 | `arduino`, `embedded`, `firmware`, `peripheral` | README | — |  |
| [shouri123/Late-Meet](https://github.com/shouri123/Late-Meet) | AI-powered Chrome extension for Google Meet with real-time transcription, meeting summaries, participant intelligence, … | `real-time`, `real-time` | description/topics | — |  |
| [Pera-Swarm/robot-library-python](https://github.com/Pera-Swarm/robot-library-python) | A modular Python library for building robot applications. It provides components for motion control, sensors, communica… | `sensors`, `sensors` | description/topics | — |  |
| [XStreamRollz/XStreamRoll](https://github.com/XStreamRollz/XStreamRoll) | XStreamRoll is an enterprise-grade streaming platform designed for developers, content creators, and organizations that… | `real-time`, `real-time` | description/topics | database, web_api |  |
| [duckdb/duckdb](https://github.com/duckdb/duckdb) | DuckDB is an analytical in-process SQL database management system | `embedded` | description/topics | database |  |
| [solutions-plug/predictIQ](https://github.com/solutions-plug/predictIQ) | PredictIQ Contracts is a comprehensive prediction market platform built on Stellar's Soroban smart contract platform. T… | `real-time` | description/topics | finance |  |
| [lapis-lang/lapis-js](https://github.com/lapis-lang/lapis-js) | An embedded DSL for experimentation of Lapis Semantics | `embedded`, `embedded` | description/topics | — |  |

### Autonomous Robotics

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [pro3d-space/PRo3D](https://github.com/pro3d-space/PRo3D) | PRo3D, short for Planetary Robotics 3D Viewer, is an interactive 3D visualization tool allowing planetary scientists to… | `Robotics` | description/topics | — |  |
| [Benned-H/robotics_utils](https://github.com/Benned-H/robotics_utils) | Catch-all repository for general-purpose robotics utilities. | `robotics`, `robotics` | description/topics | — |  |
| [D-sorganization/Tools](https://github.com/D-sorganization/Tools) | Engineering and scientific desktop applications: process calculators, signal and data processing, URDF and robotics mod… | `robotics`, `robotics`, `motion planning`, `robotics` | description/topics | scientific_computing |  |
| [ARPAHLS/aura](https://github.com/ARPAHLS/aura) | The runtime coat around agent loops. | `autonomous` | description/topics | — |  |
| [Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | Production-ready serverless automation patterns using Amazon FSx for NetApp ONTAP S3 Access Points — 17 industry use ca… | `autonomous`, `lidar`, `mapping` | README | — |  |
| [aden-hive/hive](https://github.com/aden-hive/hive) | Multi-Agent Harness for Production AI | `autonomous` | description/topics | — |  |
| [yaboyshades/super-alita](https://github.com/yaboyshades/super-alita) |  Super Alita v3.0: Production-Grade Autonomous Cognitive Agent with Dynamic Capabilities & Neural Architecture | `Autonomous` | description/topics | web_api |  |
| [srivamc/ContractIQ](https://github.com/srivamc/ContractIQ) | ContractIQ: Autonomous Contract-Driven Quality Engineering with Agentic AI for UI and Backend API automation | `Autonomous`, `autonomous` | description/topics | finance, web_api |  |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | Framework for orchestrating role-playing, autonomous AI agents. By fostering collaborative intelligence, CrewAI empower… | `autonomous`, `autonomous` | description/topics | machine_learning |  |

### Bioinformatics

| Repository | Description | Matched | From | Also matched | Correct? |
| --- | --- | --- | --- | --- | --- |
| [bmouler/codon-constrain](https://github.com/bmouler/codon-constrain) | Exact synonymous codon optimization under GC, motif, homopolymer, and flank constraints | `bioinformatics`, `dna`, `genomics`, `protein` | description/topics | — |  |
| [broadinstitute/cromwell](https://github.com/broadinstitute/cromwell) | Scientific workflow engine designed for simplicity & scalability. Trivially transition between one off use cases to mas… | `bioinformatics`, `bioinformatics` | description/topics | operating_systems |  |

## T9 — 50 random relevant commits from 2025 (manual check: agent-written?)

| Repository | Date | Agent-marked | Message (first 300 chars) | Agent? (manual) |
| --- | --- | --- | --- | --- |
| [provide-io/pyvider-cty](https://github.com/provide-io/pyvider-cty/commit/8cb4246d27650edbe48f79bb687132145553575a) | 2025-10-20 |  | qualify(property_based): add property-based tests for collections and exception coverage |  |
| [mjc/reencodarr](https://github.com/mjc/reencodarr/commit/2666754059550b85d1ba648b071d152efe4dc12c) | 2025-08-14 |  | test: Add comprehensive DataConverters and exception handling tests - Create DataConvertersResolutionTest for consolidated resolution parsing - Add ExceptionHandlingTest for encoding error scenarios - Disable property-based tests temporarily (.disabled extension) - Ensure test coverage for consolida |  |
| [stoneliuCS/fluid-oas](https://github.com/stoneliuCS/fluid-oas/commit/5dbbb385c7361bc16e20048825d0da709636babc) | 2025-05-04 |  | Might need to think about property based testing. |  |
| [aaronstevenwhite/arcweight](https://github.com/aaronstevenwhite/arcweight/commit/19d3a4b2d6bb19591158239d86e0564f1c6aad85) | 2025-07-01 |  | Moves unit tests into modules and adds comprehensive integration tests for algorithms and FST operations This commit introduces a suite of integration tests to validate the functionality and interactions of various algorithms within the FST module. The tests cover key operations such as determinizat |  |
| [JoeyScottSchronce/golang-practice-with-TDD](https://github.com/JoeyScottSchronce/golang-practice-with-TDD/commit/c759eee61de4b57d43ce41869446a193c5931a77) | 2025-10-23 |  | property based testing |  |
| [lazyxeon/AstraWeave](https://github.com/lazyxeon/AstraWeave/commit/310cfb14a7e7c73f28dac8e08963cb688e380722) | 2025-10-13 |  | added fuzz testing and property-based tests to ensure ECS reliability and correctness. |  |
| [IntersectMBO/cardano-node-tests](https://github.com/IntersectMBO/cardano-node-tests/commit/4e7ce5ea1d8b2d03e2acde945e70b22dd814a418) | 2025-09-12 |  | test(mnemonic): add property-based tests for key derivation Add property-based tests for 'derive_from_mnemonic' to verify acceptance of valid account numbers and rejection of invalid account/key numbers. Includes hypothesis-based checks for boundary values and invalid types. |  |
| [hkirk/swtafp-slides](https://github.com/hkirk/swtafp-slides/commit/c4679c85b95a7468069828b09012203c61c1861b) | 2025-09-16 |  | Updates to Property based testing |  |
| [DROOdotFOO/zmin](https://github.com/DROOdotFOO/zmin/commit/b6184a9291cbb2a0aed9b5b282701615605c20f0) | 2025-07-29 |  | test: improve test framework and add comprehensive test coverage - Fix test framework stderr output causing false failures - Re-enable concurrent processing test with thread-safe allocator - Add comprehensive dev tools integration tests - Update regression tests to work with new validation system -  |  |
| [jishengyang-cal/NautilusTrader](https://github.com/jishengyang-cal/NautilusTrader/commit/14b0752eefbe5b4c6d5af25f0b75524065e4b8eb) | 2025-06-09 |  | Consolidate property-based testing to use proptest |  |
| [niltsiar/another_todo](https://github.com/niltsiar/another_todo/commit/1a0786914c780bfebb2e31c4a20d3461e7b8cb7e) | 2025-07-18 |  | 📦 NEW: Add kotest-property dependency for property-based testing |  |
| [michaelklishin/rabbitmq-http-api-rs](https://github.com/michaelklishin/rabbitmq-http-api-rs/commit/64c8c8b291f49aa5fa423a41f5139fb64ba15b10) | 2025-09-19 |  | Fix a bug in UriBuilder#replace, more property-based tests |  |
| [Nick2bad4u/Uptime-Watcher-Docusaurus](https://github.com/Nick2bad4u/Uptime-Watcher-Docusaurus/commit/2bd287a8643acd9f060f1fd4ffe7be4acc2c3a41) | 2025-09-06 |  | 🧪 [test] Add comprehensive property-based test suites - Adds extensive property-based tests using Fast-Check for cache, chart, duration, error handling, fallback, monitor title, status, time, timeout, and validation utilities - Improves edge case coverage, invariants, and deterministic behavior chec |  |
| [marc-watters/learn-go-with-tests](https://github.com/marc-watters/learn-go-with-tests/commit/b7ab8c389ab5e4e2de58025698ca94255f3a8560) | 2025-02-03 |  | 15 - add(test): property based testing |  |
| [quex-tech/onchain-ai](https://github.com/quex-tech/onchain-ai/commit/cd20bd42bdfb46d40caf787a3c05fea087943703) | 2025-12-26 |  | Add property-based tests for messages and utils |  |
| [oluwafemidiakhoa/sundew_algorithms](https://github.com/oluwafemidiakhoa/sundew_algorithms/commit/7645cb7dcc434e837e37944629e8dc6a2e682b72) | 2025-09-17 | yes | fix: Add hypothesis dependency for property-based testing - Added hypothesis>=6 to dev dependencies in pyproject.toml - Resolves ModuleNotFoundError when running pytest on test_invariants.py - Tests now pass successfully: 43 passed in 2.48s 🤖 Generated with [Claude Code](https://claude.ai/code) Co-A |  |
| [discus0434/python-template-for-claude-code](https://github.com/discus0434/python-template-for-claude-code/commit/b2701e7ec727088deca7f8d0ac72ebb5f67d4e16) | 2025-06-15 | yes | feat: Comprehensive Python template enhancements ### Core Infrastructure - Add comprehensive type definitions with TypedDict, Literal, and JSONObject - Implement profiling utilities with decorators and context managers - Expand helper functions with chunk_list, flatten, and validation utilities - Ad |  |
| [RA80533/summit](https://github.com/RA80533/summit/commit/894edbb3ed7c1c7f30ff9636afd414414345a218) | 2025-11-20 | yes | Add property-based testing with fast-check (#11865) Introduced 'fast-check' for property-based testing in the server. Added fuzz tests for 'NarrativeSimulationEngine', 'nl2cypher', and 'dedupeAlerts'. Configured tests to be faster in CI environments. --- *PR created automatically by Jules for task [ |  |
| [yhsung/mini-mind](https://github.com/yhsung/mini-mind/commit/77012f28ce34e7abdcacde41d88f156d6519339a) | 2025-09-27 | yes | Create comprehensive graph operations unit tests - Implement comprehensive unit tests for node and edge operations - Add tests for graph traversal and validation functions - Create property-based tests for graph invariants using PropTest - Include 30 test cases covering: - Node CRUD operations with  |  |
| [glide-browser/glide](https://github.com/glide-browser/glide/commit/b975ab63790c3b485695b6e6c012e2186b4901bd) | 2025-07-14 |  | feat(tests): setup fast-check for property based testing |  |
| [helloellinor/kjernekraft](https://github.com/helloellinor/kjernekraft/commit/3700faf0feef51b4a5128fd7e14f8cc0132b04b6) | 2025-08-16 |  | Implement automated stateful property-based testing of user actions Co-authored-by: helloellinor <58392209+helloellinor@users.noreply.github.com> |  |
| [SatoryKono/bioactivity_data_acquisition](https://github.com/SatoryKono/bioactivity_data_acquisition/commit/9c50186af1179521d8c8597a5d7944198f6ce66b) | 2025-10-31 |  | Document property-based tests in audit report |  |
| [GiantBeanstalk/Speeddating](https://github.com/GiantBeanstalk/Speeddating/commit/fd10710daa81e60697aa80f5b8940db0c511df9a) | 2025-08-07 |  | Implement comprehensive testing infrastructure with Hypothesis and Faker ✅ **Testing Infrastructure Complete:** **Core Infrastructure:** - Added pytest with asyncio, coverage, xdist, and advanced plugins - Configured Hypothesis for property-based testing with realistic profiles - Set up comprehensiv |  |
| [BjornMelin/tripsage-ai](https://github.com/BjornMelin/tripsage-ai/commit/e250dcc36cb822953c327d04b139873e33500e4f) | 2025-06-11 |  | feat: implement comprehensive test suite achieving 90%+ coverage for BJO-130 features Critical Test Implementation: - Create 64 comprehensive tests for TripCollaborator Pydantic models with property-based testing - Implement 40 database service tests covering all 6 new methods with edge cases - Add  |  |
| [ImmortalDemonGod/RNA_PREDICT](https://github.com/ImmortalDemonGod/RNA_PREDICT/commit/a722a131195508837c3d9d571f3e3bfb9dd9f188) | 2025-03-29 |  | 📝 docs(test_wrapped_protenix_integration): add integration test documentation - create a comprehensive markdown file for integration tests - outline refactoring goals for test improvement - provide context on using Hypothesis for property-based testing - include input format and example test code fo |  |
| [dd-dent/hic](https://github.com/dd-dent/hic/commit/1d9de2100c479b3a80275c3aafca361b9f76b2a5) | 2025-02-10 |  | feat: Add CHOFF-aware retriever implementation - Add RetrieverAgent for intelligent message retrieval - Implement CHOFF-based relevance scoring - Add comprehensive property-based tests with state machines - Update summarizer tests |  |
| [MitsukiSUGITA/my_mongoDB](https://github.com/MitsukiSUGITA/my_mongoDB/commit/8a3805a79081b1f907a71cb41d5687e6e97d1f9e) | 2025-04-10 |  | SERVER-102716 Improve property-based test logging output (#33900) GitOrigin-RevId: 90cfdd8c19c0c99434f804db3113e8a46c7b525d |  |
| [MitsukiSUGITA/my_mongoDB](https://github.com/MitsukiSUGITA/my_mongoDB/commit/f17045f3b29a46e3f0f60235205677e297ee0e19) | 2025-04-29 |  | Revert "SERVER-93783 Model query knobs and test different configurations using property-based testing (#35378)" (#35501) Co-authored-by: auto-revert-processor <devprod-si-team@mongodb.com> GitOrigin-RevId: 0cd88e5599fd336d684b2d82f12c433f791be043 |  |
| [PitchConnect/match-list-change-detector](https://github.com/PitchConnect/match-list-change-detector/commit/43e23643e67de8840c7883ed55316221bf400bef) | 2025-07-17 |  | fix: Restore CI to run only property-based tests Critical fix: CI was running all tests instead of just tests/test_property_based.py This caused KeyError: 'http' during test collection, contradicting our Phase 1 strategy. Fixed by restoring original CI behavior: - pytest tests/ → pytest tests/test_p |  |
| [Frid-Yuandu/zipper](https://github.com/Frid-Yuandu/zipper/commit/b5c65a98939b47907972c3eefabc0c3516d7dcd4) | 2025-09-18 |  | Merge pull request #3 from Frid-Yuandu/test/add_property_based_testing_for_all_modules feat: add comprehensive property-based testing for list zipper |  |
| [Picard2305/Portfolio](https://github.com/Picard2305/Portfolio/commit/de21bdc8872662ef286184f3e1ce314927f09b51) | 2025-08-30 |  | Add files via upload Examples of property-based testing. |  |
| [paiml/ruchy](https://github.com/paiml/ruchy/commit/1e58875ccc148d4608939dc450bfaeb10ba81016) | 2025-08-16 | yes | feat: Release v0.2.1 with major REPL improvements - Added REPL state persistence for functions, structs, traits, and impls - Implemented complete string interpolation with AST support - Added comprehensive grammar coverage testing framework - Integrated property-based testing and fuzzing - Fixed all |  |
| [JandyTenedora/ShoppingBasket](https://github.com/JandyTenedora/ShoppingBasket/commit/b42deedaa9a2571befa4e6685a928b434acc952f) | 2025-02-27 |  | test(pricing): add property based tests |  |
| [itdojp/ae-framework](https://github.com/itdojp/ae-framework/commit/641a5fa5fabbdb2df1e981f95cdd393403f9a98e) | 2025-09-17 |  | test(resilience): add decorrelated jitter boundary PBTs - attempt=0 and near-max boundaries for decorrelated jitter\n- Small property-based tests; aligns with prior resilience work |  |
| [cappallo/aura](https://github.com/cappallo/aura/commit/89633f1b3578b6e18889bdd9d2de7685db4762a7) | 2025-11-09 |  | Update implementation status report with revised overall progress metrics, enhanced contract validation, and improvements to property-based testing documentation. |  |
| [DanielAvdar/activations-plus](https://github.com/DanielAvdar/activations-plus/commit/f986b21f2a411a075fe3d481efd534aa47b500d5) | 2025-04-17 |  | improving type annotations, enhancing documentation, and refining activation function implementations. (#4) * Remove HardSwish activation function from documentation Signed-off-by: DanielAvdar <66269169+DanielAvdar@users.noreply.github.com> * Add mathematical explanations for activation functions in |  |
| [duhboto/MetamorphicGuard](https://github.com/duhboto/MetamorphicGuard/commit/037b24e081c8a75d59d57e7eab75066d68defffc) | 2025-11-13 |  | Fix property-based tests: remove flaky width check and fix Bayesian CI test - Remove Property 4 (width decrease) check for Wilson interval as it's too sensitive - Fix Bayesian CI test to use correct function signature (prior_type instead of prior) - Update Bayesian CI test to use two proportions (de |  |
| [PeterFile/KnowledgeLens](https://github.com/PeterFile/KnowledgeLens/commit/68efb8f7f1fc39e256081c9fd7af716b7fc7ceb2) | 2025-12-10 |  | test(tokenizer): add property-based test for token truncation Add Property 14 test validating that truncateToTokens always produces output with token count <= maxTokens limit. Set up vitest and fast-check for property-based testing. Create tests/lib directory structure for organized test files. Impl |  |
| [f4ah6o/wrkflw.mbt](https://github.com/f4ah6o/wrkflw.mbt/commit/339fdafbc32402fa68f375369e22fe2682a5c23e) | 2025-12-30 |  | test: add property-based tests using quickcheck Add 42 property-based tests covering: - ActionInfo parsing (Docker, local, standard refs) - Trigger validation (events, cron syntax) - Step validation (action references) - Job validation (reusable workflows, normal jobs) Generators are implemented in  |  |
| [MohideenFasith/reconforge-enterprise](https://github.com/MohideenFasith/reconforge-enterprise/commit/cf1fdc65071bbe3525d16e274842d53ffd224c3b) | 2025-05-05 |  | test(reconciliation): property-based tests for matching invariants |  |
| [lgalvao/sgc](https://github.com/lgalvao/sgc/commit/661007a62897534d9ebc30956db050899a7bedde) | 2025-11-29 |  | feat: Add property-based tests for backend services and utilities - Add 'HtmlSanitizingDeserializerPropertyTest' to verify HTML sanitization. - Add 'ProcessoServicePropertyTest' to verify process creation logic. - Add 'SubprocessoWorkflowServicePropertyTest' to verify workflow state transitions. - U |  |
| [mcpadre/mcpadre](https://github.com/mcpadre/mcpadre/commit/522f6d47ebaa11dbcf5f8913dd3678ccdcda4aa7) | 2025-09-30 |  | fix: exclude path-normalized server names from property-based tests The property-based test generator was creating server names like "." and ".." which get normalized away by Node.js path.join(), causing the test assertion '/.mcpadre/servers/${serverName}' to fail when comparing against actual paths |  |
| [txloc1909/toy-optimizer](https://github.com/txloc1909/toy-optimizer/commit/8bdebe9989a5e3d160f39601a6f00bd6cf9ebf8d) | 2025-05-17 |  | start using property-based testing |  |
| [MitsukiSUGITA/my_mongoDB](https://github.com/MitsukiSUGITA/my_mongoDB/commit/7ba0d36a53ceb811d6d4ff53f00de6eeb1a95729) | 2025-06-02 |  | SERVER-93783 Model query knobs and test different configurations using property-based testing (#35546) GitOrigin-RevId: d2b304258ce30e002bd69480b7ea3eef937cab9e |  |
| [MitsukiSUGITA/my_mongoDB](https://github.com/MitsukiSUGITA/my_mongoDB/commit/bb366a301c435914879eb2406014c2232b449224) | 2025-04-28 |  | SERVER-93783 Model query knobs and test different configurations using property-based testing (#35378) GitOrigin-RevId: 1043705afddec0e1ed99f8d6b46ab74a40e39704 |  |
| [p11menova/functional-programming](https://github.com/p11menova/functional-programming/commit/d8369957af7508b33ca3de98fc6dce802b4f0358) | 2025-12-18 |  | added property-based tests |  |
| [nikoheikkila/rot-13-action](https://github.com/nikoheikkila/rot-13-action/commit/d1b77e410d696d65efca7d818d6ff01f1c7a3f55) | 2025-11-01 |  | test: improve property-based tests |  |
| [axol-io/mana](https://github.com/axol-io/mana/commit/061f1095b82c5fbb8f8303f2f6a0e3d7b1c063c2) | 2025-08-10 |  | feat: add advanced cryptography and ETH2 infrastructure Cryptography enhancements: - BLS signatures via Rust NIF with slashing protection - KZG commitments for EIP-4844 blob transactions - Native cryptographic operations for performance ETH2 infrastructure: - Consensus layer networking with LibP2P a |  |
| [TheDarkLightX/Intelligent-Daemon-Interface](https://github.com/TheDarkLightX/Intelligent-Daemon-Interface/commit/3f61469ff931f1eed29966c1cd4dab9e8e1cf806) | 2025-12-24 |  | test(zkml): Add property-based tests and Rust FFI bindings ## Property-Based Tests (Hypothesis) - test_secagg_pbt.py: 12 PBT tests - Shamir: reconstruction, subset selection, unique indices - Pairwise masking: symmetry, XOR cancellation - Multi-party: mask cancellation proof - State machine: SecAggS |  |
| [raineszm/kase](https://github.com/raineszm/kase/commit/43da15a13f8a8b53c9ade2c659702020e18b5283) | 2025-11-16 |  | Add comprehensive test suite with 98% coverage, snapshot testing, and property-based tests (#1) Implement a basic test suite with the help of copilot. |  |

## T9 — Repositories with the most relevant commits

| Repository | Relevant commits |
| --- | --- |
| ImmortalDemonGod/RNA_PREDICT | 94 |
| sagifogel/Proptics | 79 |
| MarcusDavidG/Bitsave-Stacks | 40 |
| MohideenFasith/reconforge-enterprise | 28 |
| thalerjonathan/phd | 27 |
| concordant/c-crdtlib | 26 |
| mamonu/mamonu.github.io | 26 |
| mongodb/mongo | 26 |
| cozy-labs/cozy-desktop | 25 |
| onchain-labx7yv3/marlowe-cardano | 25 |
