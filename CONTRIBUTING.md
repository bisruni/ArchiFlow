# Contributing

Bu proje guvenlik ve dogruluk odaklidir. Katki verirken asagidaki adimlari izleyin.

## Gelistirme Ortami

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m pip install -e .[dev]
```

## Kod Standartlari

```bash
black archiflow main.py
isort archiflow main.py
flake8 archiflow main.py
mypy archiflow
```

## Test

```bash
pytest
```

## Pull Request Kurallari

1. Degisiklikleri tek bir konuya odakli tutun.
2. Commit mesajlarini acik yazin.
3. Davranis degisikligi varsa README veya docs guncelleyin.
4. Veri kaybi riski olusturan degisikliklerde ek test ekleyin.

## Katki Sozlesmesi (DCO)

Bu proje Contributor Certificate of Origin (DCO) modelini kullanir.
Pull request'e giren her commit `Signed-off-by` satiri icermelidir:

```text
Signed-off-by: Ad Soyad <mail@example.com>
```

Ornek commit:

```bash
git commit -s -m "feat: duplicate summary dialog improvements"
```

`-s` parametresi sign-off satirini otomatik ekler.
