# GEOPETRA 2026 pitch deck v2 — revised outline

Source deck: `BatuanSedimen_PitchDeck_PPC_GEOPETRA2026.pptx` (kept untouched).
Source paper: `Batuan Sedimen_FullPaper_FINAL_GEOPETRA2026.pdf`. Every number below is taken
from the current deck notes, which match the final paper.

## The spine in one paragraph

Open on 100 t CO₂ in, ~98 t back, and three questions: **truk atau pipa? harga karbon berapa?
masih layak, dan seberapa?** The talk argues that the three answers depend on each other
(reservoir flow decides the pipe, reservoir retention decides the carbon credit, the schedule
decides the NPV), so answering them in silos gets them wrong. We build one framework that
computes them together, then answer the three questions in the order they were asked, each
as a reversal of what the audience expects. Close by returning to the 100 tons and one rule.

**Central question (said aloud in ch. 2):** *"Apa yang berubah kalau reservoir, logistik, dan
harga karbon dihitung bersama?"*

**Closing rule (last sentence before "terima kasih"):** *"Di skala pilot, nilai CO₂ HnP ada di
jadwal dan logistik, bukan di kredit karbon."*

## Presenters and timing (target ≈ 12 min, confirm the limit)

| # | Chapter (nav-bar label) | Presenter | Time |
|---|---|---|---|
| 1 | Pertanyaan | Raffi | 1:20 |
| 2 | Kenapa sulit | Raffi | 1:25 |
| 3 | Ruang keputusan | Raffi | 0:35 |
| 4 | Surrogate | Maulidan | 2:30 |
| 5 | Menghubungkan | Maulidan | 1:35 |
| 6 | Truk atau pipa | Falah | 1:00 |
| 7 | Harga karbon | Falah | 1:10 |
| 8 | Nilai integrasi | Falah | 0:55 |
| 9 | Penutup | Falah | 1:10 |
| | **Total** | Raffi 3:20 · Maulidan 4:05 · Falah 4:15 | **11:40** |

Handoffs: Raffi → Maulidan at the end of ch. 3, Maulidan → Falah at the end of ch. 5.

## Recurring visuals

- **The 100 CO₂ blocks** (10×10 grid). Ch. 1: 98 drain back. Ch. 5: injected − produced −
  lost = net. Ch. 7: why carbon price barely matters. Ch. 9: the callback.
- **The three question cards.** Asked in ch. 1, each lights up when its chapter starts
  (ch. 6/7/8), shown filled with answers in ch. 9.
- **The 4-module chain** (ConvLSTM → MILP → Fasilitas → Ekonomi). Built in ch. 2 as the
  answer to the silo, shrinks to a corner mini-map in ch. 4–5 and lights up the active module.
- **Nav bar** along the bottom with the 9 chapter labels above, current one highlighted.

Photos: full strength on chapter openers and findings, heavily dimmed behind build scenes.

---

## 1 · Pertanyaan — Raffi (1:20)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 1a | Dark. One well, 100 blocks go down | *(jeda 2 detik)* "Bayangkan kita menyuntikkan 100 ton CO₂ ke sebuah sumur minyak di Jatibarang." | blocks (new) |
| 1b | Blocks come back up with the oil; counter 98 | "Beberapa bulan kemudian, hampir 98 ton di antaranya keluar lagi bersama minyak." | |
| 1c | Card 1: *Truk atau pipa?* | "Dari situ muncul tiga pertanyaan. Pertama: CO₂-nya dikirim dengan truk, atau pipa?" | |
| 1d | Card 2: *Harga karbon berapa?* | "Kedua: pada harga karbon berapa proyek ini untung?" | |
| 1e | Card 3: *Masih layak? Seberapa?* | "Dan ketiga: kalau 98 ton kembali, apakah proyek ini masih layak, dan seberapa layak?" | |
| 1f | Title card on platform photo | "Selamat pagi, dewan juri. Kami Tim Batuan Sedimen: saya Raffi, bersama Maulidan dan Falahurrahman." | slide 1 bg |
| 1g | Map: Subang → Jatibarang; truck moves along the OSM-routed road (model proxy source → W01, ±76 km), captioned as not the pilot's truck route; ±180 km stays as the reported pilot figure | "Pertanyaan ini nyata. Di pilot Jatibarang, Pertamina–JOGMEC, CO₂ dibawa truk iso tank sejauh ±180 km dari Subang, karena belum ada pipa." → card 1 glows | slide 2 map |
| 1h | +86% oil rate, 0 HSE incidents, 2031 full-scale | "Pilotnya berhasil: laju minyak naik sampai 86%. Target skala penuh sekitar 2031." → card 3 glows | |
| 1i | IDX ≈ USD 4/t, thin volume → JCM/Artikel 6 (Perpres 110/2025) | "Sementara harga karbon belum pasti: IDX sekitar USD 4, kanal JCM dan Artikel 6 baru terbuka." → card 2 glows | |

Note: the background context (trilema, Permen ESDM 2/2023, Perpres 14/2024) goes into one
spoken line or the appendix; it no longer gets its own slide.

## 2 · Kenapa sulit — Raffi (1:25)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 2a | The three cards in a row | "Ketiga pertanyaan ini kelihatannya terpisah. Ternyata tidak." | |
| 2b | Arrow: *laju CO₂ per sumur* (reservoir) → card 1 | "Pipa atau truk bergantung pada berapa banyak CO₂ yang dibutuhkan tiap sumur, dan itu jawaban reservoir." | |
| 2c | Arrow: *CO₂ yang tertinggal* (reservoir) → card 2 | "Nilai kredit karbon bergantung pada berapa CO₂ yang benar-benar tertinggal, dan itu juga jawaban reservoir." | |
| 2d | Arrow: *jadwal injeksi* → all three | "Dan jadwal injeksi mengubah ketiganya sekaligus." | |
| 2e | Silo queue: Reservoir → Fasilitas → Logistik → Ekonomi, hourglass between each | "Dalam praktik, keempat bagian ini dikerjakan tim berbeda, berurutan. Tiap tim menunggu tim sebelumnya, dan kalau harga atau jadwal berubah, semuanya diulang." | slide 9 (silo row) |
| 2f | Literature dropped onto single boxes: Halinda 2023 / Kristanto 2025 → reservoir (pilot, sumur tunggal); He 2026 → surrogate, berhenti di akurasi; optimasi infrastruktur → logistik, asumsi pipa | "Literatur juga begitu: tiap studi menjawab satu kotak." | slide 3 + 14 text |
| 2g | Central question, large | "Jadi pertanyaan kami: apa yang berubah kalau reservoir, logistik, dan harga karbon dihitung bersama?" | |
| 2h | The silo boxes slide into the 4-module chain (one API, provenans) | "Untuk menjawabnya, kami membangun satu kerangka: empat modul dalam satu alur, tanpa serah-terima manual." | fig01 → shapes |

## 3 · Ruang keputusan — Raffi (0:35)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 3a | 177 MRST runs as tiles; "proksi berjangkar Jatibarang, data publik" | "Kami terapkan pada studi kasus berjangkar Jatibarang, dari data publik: 177 simulasi MRST sebagai geologi," | fig02 panel b |
| 3b | Counter: 20 sumur × 162 jadwal = **3.240** | "20 sumur kandidat, 162 jadwal per sumur: 3.240 skenario," | fig02 panel c |
| 3c | × 4 harga karbon (4 / 20 / 40 / 50) × 160 re-solve | "diuji pada empat harga karbon dan 160 penyelesaian ulang Monte Carlo." | fig02 panel d |
| 3d | Handoff | "Setiap skenario butuh simulasi reservoir. Bagaimana kami menghitungnya, akan dijelaskan Maulidan." *(serahkan clicker)* | |

## 4 · Surrogate — Maulidan (2:30)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 4a | Grey bar: 5,4 min × 3.240 = 292 jam (≈1,7 minggu) | "Terima kasih, Raffi. Satu simulasi penuh MRST rata-rata 5,4 menit. Untuk 3.240 skenario: 292 jam, hampir dua minggu, dan itu baru sekali jalan." | slide 6 chart (redrawn) |
| 4b | x → MODEL → y | "Solusinya surrogate. Seperti kebanyakan model AI, ia dilatih menebak keluaran y dari masukan x." | APOGCE s2a |
| 4c | "Bhinneka Tunggal" → LLM → "Ika" | "Model bahasa seperti ChatGPT diberi potongan teks, lalu menebak kata berikutnya." | APOGCE s2b |
| 4d | plume(t) + jadwal → ConvLSTM → plume(t+1) | "Surrogate kami diberi kondisi reservoir sekarang dan jadwal injeksi, lalu menebak kondisi reservoir berikutnya." | fig03 tiles |
| 4e | **Conv**: kernel sweeps the 64×64 grid around the well | "Kenapa ConvLSTM? Bagian *Conv* melihat ruang: plume menyebar di sekitar sumur." | new |
| 4f | **LSTM**: memory cell carries the last cycle forward | "Bagian *LSTM* mengingat waktu: apa yang terjadi di siklus injeksi dan soak sebelumnya." | new |
| 4g | Three expert heads: injeksi / soak / produksi; L = L_data + λ·L_fisika; massa CO₂ direkonsiliasi CoolProp | "Tiap fase punya kepala sendiri, karena injeksi, soak, dan produksi berperilaku berbeda. Fisika masuk ke fungsi loss, dan massa CO₂ dilacak dengan neraca massa." | slide 7 text |
| 4h | Rollout chain: step → step → … 24 | "Rantai tebakan ini kami jalankan 24 langkah, satu skenario utuh." | APOGCE s50–53 |
| 4i | Bars: 292 jam vs ~1,3 jam vs 5,5 menit (cache); 1,76 s/rollout, ≈180× | "Hasilnya 1,76 detik per rollout, sekitar 180 kali lebih cepat. 3.240 skenario selesai dalam ±1,3 jam, dan penapisan ulang dari cache 5,5 menit." | slide 6 chart |
| 4j | Rows revealed one by one: MRST / prediksi / selisih | "Tapi cepat saja tidak cukup. Baris atas MRST, tengah prediksi kami, bawah selisihnya, hampir kosong." | fig03 panel a |
| 4k | Full-horizon numbers first: minyak 1,07% · gas 0,98% · massa CO₂ 3,35%; small: R² 0,9999, IoU 0,9756 (satu langkah) | "Yang kami nilai adalah galat sepanjang horizon penuh: minyak 1,07%, massa CO₂ 3,35%. Angka satu langkah memang tinggi, tapi itu bukan ukuran yang penting." | slide 7 |
| 4l | Error vs horizon, shaded beyond step 24 | "Kami juga jujur soal batasnya: kami hanya memvalidasi sampai 24 langkah. Di luar itu galat minyak masih kecil, tapi tidak kami klaim, jadi prediksinya diberi penanda keyakinan rendah; inventori gas juga lebih lemah (hingga ±15%). Ujian sebenarnya adalah keputusannya, dan itu akan dibahas Falah." *(The bundle data shows oil error does not rise past step 24, so the limit is framed as the validated range, not as degradation.)* | fig03 panel c |

## 5 · Menghubungkan — Maulidan (1:35)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 5a | Mini-map, MILP lit. Map: Subang + 20 wells, A* routes on SRTM (eksklusi permukiman 75 m, penalti sungai) | "Prediksi surrogate mengalir ke Modul 2, MILP logistik. Rute dicari di atas peta elevasi nyata," | slide 2 map, fig05 |
| 5b | Each well gets two edges: pipa / truk | "dan untuk tiap sumur MILP memilih: dipasok dengan pipa, atau truk." | |
| 5c | Pipe cross-section: v_min 1 m/s, 6 in → ṁ_min = 15,95 kg/s; failed arc stamped `below_minimum_hydraulic_flow` | "Setiap pipa dicek hidrolikanya. Pipa 6 inci baru layak di atas 15,95 kg/s. Ingat angka ini. Pipa yang gagal ditolak dengan alasan tercatat, asumsinya tidak dilonggarkan." | slide 8 eq |
| 5d | Mini-map, Fasilitas lit. Recompression, pump, separation, dehydration; parity CoolProp vs DWSIM 8/8 | "Modul 3 men-sizing fasilitas; hasilnya cocok dengan DWSIM di delapan kasus." | fig06 a |
| 5e | Mini-map, Ekonomi lit. Blocks: diinjeksi − terproduksi − rugi = **neto** (ISO 27916) | "Modul 4 adalah ekonomi dua sisi: minyak tambahan plus kredit karbon, tapi kreditnya hanya atas CO₂ yang tersimpan neto." | blocks |
| 5f | Harga karbon arrow loops back into the MILP objective | "Dan harga karbon masuk langsung ke fungsi tujuan MILP, jadi harga bisa mengubah sumur yang dipilih." | |
| 5g | Workbench screenshot | "Semua ini satu software: impor geologi dan jalan, putar plume per sumur, peringkat portofolio per harga karbon, dan setiap angka punya jejak sumbernya." | slide 14 screenshot |
| 5h | Handoff: the three cards return | "Sekarang kita jalankan untuk tiga pertanyaan tadi. Falah." *(serahkan clicker)* | |

## 6 · Truk atau pipa — Falah (1:00)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 6a | Card 1 lit, truck photo | "Terima kasih, Maulidan. Pertanyaan pertama: truk atau pipa?" | slide 11 bg |
| 6b | Expectation: "Program CCUS → pipa" | "Untuk program CCUS, jawaban biasanya pipa. Literatur optimasi infrastruktur pun menganggap begitu." | |
| 6c | Bar 15,95 kg/s next to a sliver 0,195 kg/s (≈17 t/hari) | "Tapi surrogate bilang kebutuhan tiap sumur hanya 0,195 kg/s. Sekitar 80 kali di bawah ambang pipa." | new |
| 6d | Every pipe lateral rejected; **160/160 → truk**, 8 wells | "Semua lateral pipa ditolak. Di 160 dari 160 skenario, MILP memilih truk, persis seperti praktik pilot Jatibarang." | fig05 a |
| 6e | Scale slider → crossover: hibrida > ~0,5 Mt/tahun (14,4 vs 14,6 USD/t at 0,56 Mt; 11,8 vs 14,6 at 1 Mt) | "Tapi naikkan skalanya, dan di atas ±0,5 juta ton per tahun, trunk pipa ditambah truk segmen akhir jadi lebih murah." | fig05 b |
| 6f | Answer card: *Truk di pilot, hibrida di skala komersial* | "Jawaban pertama: moda pasok adalah fungsi skala." | |

## 7 · Harga karbon — Falah (1:10)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 7a | Card 2 lit | "Pertanyaan kedua: harga karbon." | |
| 7b | Map, 8 selected wells; price ticker USD 4 | "Harga karbon kami naikkan dari USD 4 …" | fig07 a (as map) |
| 7c | Ticker 20 → 40 → 50; wells stay put; only W02 → W20 at ≥ USD 40 | "… sampai USD 50, dua belas kali lipat. Rencananya pasti berubah, kan? Ternyata tidak. Delapan sumur yang sama terpilih di 39 dari 40 skenario." | |
| 7d | NPV 16,50 → 16,52 juta USD; impas USD 0/t; regret maks ≈ USD 19 rb (≈0,1%) | "NPV hampir tidak bergerak. Proyek sudah untung tanpa kredit karbon, dan salah menebak harga paling mahal sekitar USD 19 ribu." | fig07 b, c |
| 7e | Blocks again: 100 → 98 back → ~58 t neto per sumur (30–103 t) ≈ USD 3 rb at USD 50/t | "Kenapa? Kembali ke 100 ton tadi. Hanya sekitar 58 ton tersimpan neto per sumur; di USD 50 pun nilainya sekitar USD 3 ribu." | blocks |
| 7f | Gross vs net: ≈45× too high | "Kalau CO₂ yang diinjeksi langsung dikreditkan, nilainya terlalu tinggi 45 kali." | slide 12 |
| 7g | Answer card: *Harga karbon tidak mengubah rencana pilot* | "Jawaban kedua: bisnis pilot HnP jangan bertumpu pada kredit karbon. Tuas harga karbon bekerja lewat skala program dan desain yang memaksimalkan retensi." | |

## 8 · Nilai integrasi — Falah (0:55)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 8a | Card 3 lit | "Pertanyaan ketiga: kalau kredit karbon tidak menolong, dari mana nilainya?" | |
| 8b | Arm A: one uniform schedule for every well (9.000 m³/hari, 3 siklus, mirip pilot) vs Arm C: per-well screening; "selain itu identik" | "Kami bandingkan praktik tersilo, satu jadwal seragam untuk semua sumur, dengan penapisan terintegrasi. Selain itu semuanya sama." | slide 13 |
| 8c | Screening surface: only 3 of 162 schedules ever chosen, all more intensive (10.000 m³/hari, soak 25–30, 4 siklus) | "Dari 162 jadwal, hanya 3 yang pernah terpilih, dan semuanya lebih intensif dari jadwal seragam." | fig04 |
| 8d | Bars grow: 11,27 → 16,52 juta USD, **+46,6%**, at all four prices | "Hasilnya NPV portofolio naik dari 11,27 menjadi 16,52 juta USD, +46,6%, di keempat harga karbon." | fig08 a |
| 8e | MRST check: top-5 plans re-simulated, NPV diff 1,3% (maks 3,2%), top stays top | "Dan ujian sebenarnya: lima rencana terbaik kami simulasi ulang dengan MRST. Selisihnya rata-rata 1,3%, dan rencana teratas tetap teratas." | fig08 c |
| 8f | Answer card: *Layak tanpa kredit karbon; +46,6% dari jadwal & logistik* | "Jawaban ketiga: layak, dan nilainya datang dari menghitung semuanya bersama." | |

## 9 · Penutup — Falah (1:10)

| Scene | On screen | Spoken (draft) | Asset |
|---|---|---|---|
| 9a | The three answered cards side by side | "Jadi, tiga pertanyaan, tiga jawaban." *(one line each)* | |
| 9b | Staged pathway: ① uji antarsumur: truk + jadwal intensif → ② trunk hibrida > 0,5 Mt/tahun → ③ kredit karbon di skala komersial | "Untuk Jatibarang kami sarankan jalur bertahap: uji antarsumur dengan truk dan jadwal intensif, pipa hibrida saat skala membesar, lalu kredit karbon menjadi pendorong nilai di skala komersial." | slide 15 |
| 9c | Kenapa bisa dipercaya: tiap modul tervalidasi · 5 rencana dicek MRST · horizon 24 langkah ditandai. Batasan (small): data proksi publik, biaya kelas penapisan (bukan FEED), presipitasi garam belum dimodelkan, jadwal terpilih di batas atas grid, Arm B belum dijalankan | "Kenapa hasil ini bisa dipercaya: setiap modul divalidasi, rencana terbaik dicek ulang dengan simulator penuh, dan batasnya kami tandai sendiri." | slide 15 |
| 9d | Blocks: 98 return … then +46,6% | *(jeda, tatap juri)* "Kembali ke 100 ton tadi. Ya, hampir 98 ton kembali ke permukaan. Tapi dengan jadwal dan moda pasok yang tepat, proyek yang sama menghasilkan 46,6% lebih banyak nilai." | blocks |
| 9e | The closing rule | "Di skala pilot, nilai CO₂ HnP ada di jadwal dan logistik, bukan di kredit karbon." | |
| 9f | Terima kasih (sunset photo) | "Demikian presentasi Tim Batuan Sedimen. Terima kasih." | slide 16 |

## Backup (not presented)

Daftar Pustaka, then Lampiran A–E unchanged in content, restyled lightly. Add **Lampiran F:
arsitektur dua tahap** (full fig01: screening → biaya riil → audit diskrepansi → re-solve →
konfirmasi top-K MRST), since the main talk shows only the 4-module chain.

## Changes from v1

- Raffi opens, Maulidan takes the surrogate and integration chapters, Falah unchanged.
- The hook's questions are reordered to match the findings and become the outline.
- Latar is folded into the hook, one fact per question; the gap slide becomes the
  dependency web plus the silo queue; literature positioning moves there from slide 14.
- "Kenapa satu software" (slide 9) becomes scene 2e; the software screenshot (slide 14)
  becomes the bridge into the findings (5g).
- Validation leads with full-horizon errors and defers to the MRST decision check, instead of
  leading with one-step R².
- Findings are told as expectation → reversal.
- Limitations are reframed as "kenapa bisa dipercaya" and the talk ends on one rule.
