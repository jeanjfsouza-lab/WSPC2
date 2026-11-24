# Vehicle audio pipeline — sources and licences

Everything downloaded or cloned lives in the git-ignored `Saved/Audio/Pipeline/`. What reaches the game are the
WAVs rendered or synthesised by the scripts in this folder, imported into `Content/Audio/Vehicles/`.

| Source | Version | Licence | Used for |
|---|---|---|---|
| [Vangardo/engine-sim-unity-audio](https://github.com/Vangardo/engine-sim-unity-audio) | commit `77080ca72765` | MIT (Copyright 2026 Vangardo) | Offline generator `EngineAudioGenerator.exe`: dyno capture, whole-cycle loop cutting, bank JSON. Its own presets are **not** used (they carry third-party authorship). |
| Engine Simulator runtime, vendored in the generator (`ThirdParty/engine-sim-runtime`), upstream [ange-yaghi/engine-sim](https://github.com/ange-yaghi/engine-sim) | upstream commit `85f7c3b959a9` | MIT (Copyright 2022 AngeTheGreat / Ange Yaghi) | Simulation core, and the base presets of every archetype in `presets/` (`07_gm_ls`, `chev_truck_454`, `06_even_fire_v6`, `04_60_degree_v6`, `05_honda_vtec`, `02_subaru_ej25_uh`, `03_2jz`, `12_ferrari_412_t2`), retuned by `make_engine_presets.py`. |
| [ange-yaghi/engine-sim](https://github.com/ange-yaghi/engine-sim) | commit `85f7c3b959a9` | MIT | Reference copy of the same presets. |
| [Engine-Simulator/engine-sim-community-edition](https://github.com/Engine-Simulator/engine-sim-community-edition) | commit `4e5c20da3e2c` | none declared | Reference only; nothing copied. |
| [kirbyguy22/engine-sim-garage](https://github.com/kirbyguy22/engine-sim-garage) | commit `980722d3724a` | none declared | Reference only; nothing copied. |
| [DasEtwas/enginesound](https://github.com/DasEtwas/enginesound) | commit `e5fcca587397` | MIT | Cloned as a procedural fallback; not needed (every archetype rendered in engine-sim). |
| [zolaski333/EngineLab](https://github.com/zolaski333/EngineLab) | commit `bdfd88574cb2` | MIT | Cloned as reference only. |
| [Kenney — Impact Sounds](https://kenney.nl/assets/impact-sounds) | ZIP SHA-256 `029d734af1582474edf3a694d1b0cebc97c1c152f2f39fa34d4c2bafc5de77f8` (800 850 bytes, 130 OGG) | CC0 | Metal, plate, punch, tin and glass hits layered into the impacts, crunches, glass and backfires (`build_collision_and_mech_sfx.py`; each file lists its Kenney sources in `CollisionAudioManifest.json`). |
| Hugging Face `Jacob121294/bank-sfx` | — | declares CC0, provenance not verifiable | Not used. |
| Sonniss #GameAudioGDC bundles | — | royalty-free in games, no redistribution, no AI/ML training | Not used. `fetch_sonniss_optional.ps1` filters a bundle the user downloads by hand into the git-ignored `Content/Audio/Vehicles/ThirdParty/` source folder. |

The archetype presets in `presets/` are derivative works of the MIT presets above and keep the attribution in
their headers. All other sounds (sub-bass, metal modes, crackle, scraping, tyres, turbo, supercharger, gears,
diesel knock) are synthesised from scratch.
