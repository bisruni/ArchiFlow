Configuration Guide
===================

Bu bolum uygulamanin mevcut ayar noktalarini ozetler.

Runtime Secimleri
-----------------

Uygulama davranisi asagidaki seceneklerle degisir:

- Is akisi (`scope`): gruplama/kopya temizleme kapsamı
- Tasima modu (`mode`): copy veya move
- Kopya modu (`dedupe`): off, quarantine veya delete
- Dry-run: dosya degisikligi olmadan simule calisma
- Benzer goruntu analizi: Pillow varsa aktiflestirilebilir

Config.yaml
-----------

Kalici konfigurasyon dosyasi:

.. code-block:: text

   ./.archiflow/config.yaml

Temel alanlar:

- `default_scope`
- `default_mode`
- `default_dedupe`
- `default_dry_run`
- `default_similar_images`
- `default_profile`
- `log_level`, `console_log_level`, `log_dir`

CLI Parametre Tabanli Konfigurasyon
-----------------------------------

CLI argumanlari config degerlerini override eder.
Ek olarak `apply` ve `preview` komutlarinda `--profile` ile profil secilebilir.

Ortam Degiskenleri
------------------

Logging tarafinda desteklenen ortam degiskenleri:

- `ARCHIFLOW_LOG_LEVEL`: `DEBUG`, `INFO`, `WARNING`, `ERROR`
- `ARCHIFLOW_CONSOLE_LOG_LEVEL`: konsol cikis seviye filtresi
- `ARCHIFLOW_LOG_DIR`: log dosyalarinin yazilacagi klasor
- `ARCHIFLOW_CONFIG_FILE`: varsayilan config dosya yolunu degistirir
- `ARCHIFLOW_PROFILE_PATH`: varsayilan profil dosya yolunu degistirir
- `ARCHIFLOW_DEFAULT_SCOPE`, `ARCHIFLOW_DEFAULT_MODE`, `ARCHIFLOW_DEFAULT_DEDUPE`
- `ARCHIFLOW_DEFAULT_DRY_RUN`, `ARCHIFLOW_DEFAULT_SIMILAR_IMAGES`, `ARCHIFLOW_DEFAULT_PROFILE`

Log Dosyasi Varsayilani:

.. code-block:: text

   ./.archiflow/logs/archiflow.log

Profil Konfigurasyonu
---------------------

Profil kayitlari `ProfileService` ile JSON dosyasinda tutulur.

Platforma gore varsayilan profil yolu:

- macOS: `~/Library/Application Support/ArchiFlow/profiles.json`
- Linux: `${XDG_CONFIG_HOME:-~/.config}/ArchiFlow/profiles.json`
- Windows: `%APPDATA%\\ArchiFlow\\profiles.json`

Not:
Eski `ArchiFlow/profiles.json` yolu varsa geriye donuk uyumluluk icin kullanilir.

Islem Kayitlari ve Rapor Klasorleri
-----------------------------------

Transaction kayitlari:

.. code-block:: text

   <target>/.archiflow/transactions/

Otomatik raporlar:

.. code-block:: text

   <target>/.archiflow/reports/

Karantina:

.. code-block:: text

   <target>/.archiflow_quarantine/<timestamp>/
