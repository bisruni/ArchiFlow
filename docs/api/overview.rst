API Genel Bakis
===============

Bu bolum modullerin sorumluluklarini ve birbiriyle iliskilerini ozetler.

Temel Servisler
---------------

- ``archiflow.scanner``: Dosya sistemi taramasi ve ``FileRecord`` uretimi.
- ``archiflow.duplicate_detector``: Kopya tespiti (boyut -> hizli imza -> SHA-256 -> byte karsilastirma).
- ``archiflow.organizer``: Gruplama/duzenleme ve kopya islemleri (karantina/silme) uygulamasi.
- ``archiflow.transaction_service``: Islem gunlugu kaydi ve geri alma (undo).
- ``archiflow.pipeline``: Servisleri orkestre eden ana motor.

Arayuz Katmanlari
-----------------

- ``archiflow.cli``: Komut satiri giris noktasi.
- ``archiflow.gui``: Ana pencere.
- ``archiflow.gui_components``: Dialoglar ve worker sinifi.
- ``archiflow.gui_theme``: Tema uygulama yardimcilari.
- ``archiflow.gui_texts``: GUI metinleri ve secim listeleri.

Ortak Moduller
--------------

- ``archiflow.models``: Paylasilan dataclass ve enum tipleri.
- ``archiflow.constants``: Sabitler ve ortak path yardimcilari.
- ``archiflow.hash_cache``: Hash cache katmani.
- ``archiflow.errors``: Ozel exception ve hata metni standartlari.
- ``archiflow.logger``: Yapilandirilmis logger ayarlari.
- ``archiflow.utils`` ve ``archiflow.validators``: Yardimci fonksiyonlar.

Type Hints Dokumantasyonu
-------------------------

Bu API sayfalari type hint bilgisini parametre/aciklama bloklarinda gosterir:

- ``autodoc_typehints = "description"``
- ``always_document_param_types = True``
- ``autodoc_typehints_format = "short"``

Boylece fonksiyon imzalarindaki tipler hem okunabilir hem de Sphinx ciktilarinda acikca gorunur.
