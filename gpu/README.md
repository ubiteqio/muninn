# Muninns KI-Maschine auf Windows

Alles, was eine Grafikkarte braucht, in einem Docker-Stapel: das Modell, das Bilder beschreibt,
und die beiden, die Vektoren daraus machen. Muninn selbst läuft woanders und spricht beide über
das Netz an.

| Container | Modell | Port | Wofür |
| --- | --- | --- | --- |
| `vllm` | Qwen3-VL-8B-Instruct | 8000 | Beschreibung, Stichworte, Szene, Text im Bild |
| `embed` | SigLIP 2 | 8100 | Bildvektoren — „Hund am Strand" findet Fotos ohne Beschreibung |
| `embed` | BGE-M3 | 8100 | Textvektoren der Beschreibung |

Zwei Container für drei Modelle: Ein vLLM-Prozess bedient immer genau ein Modell, der
Einbettungsdienst trägt beide Vektormodelle in einem.

## 1. Voraussetzungen

- **Windows 11** mit einer NVIDIA-Karte und aktuellem Treiber (Studio oder Game Ready, ab 555).
  Der Treiber gehört auf **Windows**, nicht in WSL.
- **WSL 2**: in einer Administrator-PowerShell `wsl --install`, danach neu starten.
- **Docker Desktop** mit WSL-2-Backend (Einstellungen → General → *Use the WSL 2 based engine*).

Prüfen, ob Docker die Karte sieht:

```powershell
docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

Erscheint die Tabelle mit deiner Karte, ist alles Nötige da. Erscheint sie nicht, fehlt der
Treiber auf Windows oder Docker Desktop läuft noch im Hyper-V-Backend.

### Wenn Docker Desktop „Virtualization support not detected" meldet

Dann fehlt nicht Docker, sondern die Virtualisierung darunter. Der Reihe nach:

1. **Ist sie in der Firmware an?** Task-Manager → Leistung → CPU, Zeile *Virtualisierung*. Steht
   dort „Deaktiviert", im BIOS/UEFI einschalten: bei Intel **VT-x** (oft „Intel Virtualization
   Technology"), bei AMD **SVM Mode**. Das ist der häufigste Fall.
2. **Sind die Windows-Funktionen da?** In einer Administrator-PowerShell:

   ```powershell
   dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
   dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
   ```

   Danach neu starten, dann `wsl --update` und `wsl --set-default-version 2`.
3. **Startet der Hypervisor überhaupt?**

   ```powershell
   bcdedit /set hypervisorlaunchtype auto
   ```

   Neu starten. (Steht er auf `off`, hat ihn meist ein Spiel oder ein Optimierungswerkzeug
   abgeschaltet.)
4. **Läuft etwas dagegen?** VirtualBox in alter Fassung, BlueStacks und manche Anti-Cheat-Treiber
   belegen die Virtualisierung exklusiv. Testweise beenden.

Prüfen lässt sich alles zusammen mit:

```powershell
systeminfo | Select-String "Hyper-V", "Virtualisierung", "Virtualization"
```

### Ohne Docker Desktop, direkt in WSL

Bleibt Docker Desktop störrisch, geht derselbe Stapel auch ohne es — die Docker-Engine wird in
der WSL-Distribution installiert. In einer Ubuntu-WSL-Sitzung:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo service docker start

# Damit Container die Karte sehen:
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo service docker restart

docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi
```

Auch hier braucht WSL selbst **keinen** NVIDIA-Treiber — der auf Windows genügt. Der Stapel läuft
dann wie beschrieben, nur aus der WSL-Sitzung heraus. Eines ist dabei anders: Ports aus WSL sind
nicht automatisch im Heimnetz sichtbar, dafür braucht es die Weiterleitung, die bei Docker
Desktop entfällt:

```powershell
wsl hostname -I     # die WSL-Adresse, z. B. 172.22.3.4
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=<WSL-IP> connectport=8000
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8100 connectaddress=<WSL-IP> connectport=8100
```

## 2. Dateien holen

```powershell
git clone <dein-muninn-repository> C:\muninn
cd C:\muninn\gpu
```

Gebraucht werden nur die Ordner `gpu/` und `embed/` — `embed` wird aus dem Quelltext gebaut.

## 3. Konfiguration anlegen

```powershell
Copy-Item .env.example .env
notepad .env
```

Einzutragen ist vor allem der Schlüssel, den beide Dienste verlangen:

```powershell
# erzeugt einen zufälligen Schlüssel
-join ((48..57) + (97..122) | Get-Random -Count 48 | ForEach-Object {[char]$_})
```

Das Ergebnis nach `AI_API_KEY=` schreiben. Derselbe Schlüssel kommt später in alle drei
KI-Profile in Muninn.

## 4. Starten

```powershell
docker compose up -d
```

Der erste Start lädt die Gewichte — je nach Leitung eine Viertelstunde und mehrere Gigabyte.
Zusehen:

```powershell
docker compose logs -f vllm
docker compose logs -f embed
```

Fertig ist vLLM, wenn dort `Application startup complete` steht; `embed` meldet je Modell eine
Zeile `Loading …`.

## 5. Nachsehen, ob beide antworten

Auf der Maschine selbst:

```powershell
$key = (Get-Content .env | Select-String '^AI_API_KEY=').ToString().Split('=')[1]
curl.exe -s -H "Authorization: Bearer $key" http://localhost:8000/v1/models
curl.exe -s -H "Authorization: Bearer $key" http://localhost:8100/v1/models
```

Die erste Zeile nennt `Qwen/Qwen3-VL-8B-Instruct`, die zweite `siglip2`, `bge-m3`,
`whisper-large-v3-turbo` und `buffalo_l`.

Vom Rechner, auf dem Muninn läuft, mit der IP-Adresse der Windows-Maschine statt `localhost`.
Antwortet dort nichts, liegt es an der Windows-Firewall — beim ersten Start fragt sie einmal und
die Antwort muss **Privates Netzwerk zulassen** lauten. Nachträglich, in einer
Administrator-PowerShell:

```powershell
New-NetFirewallRule -DisplayName "Muninn KI" -Direction Inbound -Protocol TCP `
  -LocalPort 8000,8100 -Action Allow -Profile Private
```

Docker Desktop veröffentlicht die Ports selbst auf allen Schnittstellen; eine Weiterleitung nach
WSL (`netsh interface portproxy`) ist **nicht** nötig.

## 6. In Muninn eintragen

Unter **Admin → KI**, ein Profil je Schnittstelle, alle mit demselben Schlüssel:

| Schnittstelle | Basis-URL | Modell |
| --- | --- | --- |
| Beschreiben | `http://<windows-ip>:8000/v1` | `Qwen/Qwen3-VL-8B-Instruct` |
| Bildvektoren | `http://<windows-ip>:8100/v1` | `siglip2` |
| Textvektoren | `http://<windows-ip>:8100/v1` | `bge-m3` |
| Sprache | `http://<windows-ip>:8100/v1` | `whisper-large-v3-turbo` |
| Gesichter | `http://<windows-ip>:8100/v1` | `buffalo_l` |

Der Modellname ist der, unter dem der Dienst ihn führt — bei vLLM genau die Zeichenkette, mit der
er gestartet wurde, samt Hersteller-Präfix. Danach in jedem Profil **Verbindung testen**; es
antwortet mit dem Modellnamen und der Anzahl der Dimensionen.

## 7. Speicher der Karte aufteilen

vLLM reserviert sich den Anteil, der in `VLLM_GPU_FRACTION` steht, und lässt den Rest liegen.
Voreingestellt sind **0.66**, damit die beiden Vektormodelle und Whisper (zusammen rund 5 GB in
halber Genauigkeit) und der Windows-Desktop noch danebenpassen. Auf einer 24-GB-Karte bleiben vLLM
damit rund 16 GB: 10 GB für die FP8-Gewichte, der Rest für den KV-Cache (rund 37.000 Tokens,
Muninn braucht etwa 30.000). Wer vorher `0.75` oder mehr in seiner `.env` stehen hatte, setzt dort
`0.66`: Bei 0.75 lief die Karte voll, Windows lagerte Grafikspeicher in den Arbeitsspeicher aus,
und alles auf der Karte lief nur noch im Schneckentempo.

Gerät der Start von `embed` mit `CUDA out of memory` ins Stocken, ist vLLM zu gierig — Anteil
senken und `docker compose up -d` erneut.

## Betrieb

| | |
| --- | --- |
| Automatisch mitstarten | Docker Desktop → *Start Docker Desktop when you log in*. Die Container tragen `restart: unless-stopped` und kommen dann von selbst hoch. |
| vLLM erneuern | `VLLM_VERSION` in `.env` auf die neue Fassung setzen, `docker compose up -d`, dann `docker compose logs -f --since 5m vllm` bis `Application startup complete`. Bricht sie mit `No available memory for the cache blocks` ab, die alte Nummer zurück. |
| Modelle wechseln | Eintrag in `.env` ändern, `docker compose up -d`. Die Gewichte liegen im Volume `models` und werden nur einmal geladen. |
| Aufräumen | `docker compose down` hält an, `docker compose down -v` wirft auch die geladenen Gewichte weg. |
| Auslastung sehen | `nvidia-smi` auf Windows, oder `docker stats`. |

## Wenn etwas klemmt

| Symptom | Ursache |
| --- | --- |
| `could not select device driver "nvidia"` | Docker sieht die Karte nicht: Treiber auf Windows prüfen, Docker Desktop neu starten. |
| vLLM bricht beim Laden ab, ohne Fehler | Gemeinsamer Speicher zu klein. Der Stapel setzt dafür `ipc: host`; wird die Datei verändert, muss das drin bleiben. |
| vLLM startet immer wieder neu, im Log ein negativer KV-Cache | Zu wenig Speicher neben den Vektormodellen. Der Stapel lädt deshalb die FP8-Gewichte, begrenzt auf ein Bild ohne Video je Anfrage und acht gleichzeitige Anfragen und startet vLLM erst nach `embed`. Hilft das nicht, `VLLM_MAX_MODEL_LEN` oder `VLLM_GPU_FRACTION` in `.env` anpassen. |
| `RuntimeError: UVA is not available` | Der neue Modell-Läufer (V2) braucht angehefteten Hostspeicher, den WSL 2 nicht anbietet. Der Stapel setzt deshalb `VLLM_USE_V2_MODEL_RUNNER=0`. Bei neuem WSL-Kern geht auch `VLLM_WSL2_ENABLE_PIN_MEMORY=1`. |
| `Unauthorized` in Muninn | Der Schlüssel im Profil stimmt nicht mit `AI_API_KEY` überein. |
| `gibt es dort nicht. Endet die Basis-URL auf /v1?` | Die Adresse im Profil endet nicht auf `/v1`. |
| Antwortet nur auf der Maschine selbst | Windows-Firewall, siehe Schritt 5. |
