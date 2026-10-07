# Movimento dell'app Tk 5.0

Un gestore condiviso usa `after(34)` (meno di 30 fps). Il tempo dell'effetto avanza solo quando l'app è visibile/in primo piano e c'è stata interazione negli ultimi 5 secondi. In pausa resta un controllo da 250 ms, senza ridisegni; l'evento input riattiva il clock. Effetti finiti normalmente 80–540 ms; indicatori continui solo quando necessari. Nessun contatore o dato della persona animato.

«Riduci animazioni»: preferenza personale `sistema`, `ridotte`, `complete`. Default sistema, legge Windows `SPI_GETCLIENTAREAANIMATION` (0x1042); lettura fallita o piattaforma non Windows → ridotte. Nessuna modifica alle impostazioni Windows. Riduzione immediata, controlli e stato sempre testuali. [API Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-systemparametersinfow).

| Effetto | Tk | Fedeltà rispetto al mockup |
|---|---|---|
| Splash, fade e zoom dello stemma | Toplevel alpha + logo proporzionale, 540 ms totali; barra nella seconda parte | Fedele al principio fade/zoom; composizione e barra più semplici |
| Intestazione | Riflesso a bassa intensità in una sottile fascia, ciclo 6 s | Approssimato: non gradiente CSS sull'intera intestazione |
| Schermate | Slide verticale 6 px, 180 ms, senza attese aggiunte | Slide fedele; fade dei singoli widget non disponibile, omesso |
| Schede hover | Bordo che assume un colore di elevazione in 160 ms; angoli arrotondati disegnati | Approssimato: non sposta il layout e non crea un'ombra dinamica |
| Pulsanti | Colore hover 120 ms e pressione 1 px per 80 ms | Fedele, con rendering Tk |
| Raccolta in corso | Cerchio con pulsazione di raggio minima, 2 s; etichetta esplicita | Fedele; in consuntivo dice giornata in corso, senza fingere raccolta |
| Chip | Comparsa sequenziale tramite colore, 180 ms; scaglionamento <=150 ms, primi 18 | Approssimato: niente opacità CSS/traslazione dei chip; etichetta sempre leggibile |
| Sintesi e PDF | Barra indeterminata + fascia shimmer tenue, 1,4 s; testo preparazione | Approssimato: shimmer sotto il testo, senza coprirlo; non percentuale di completamento |
| VALIDO | Spunta vettoriale che si disegna, 400 ms, stato testuale | Fedele |
| ALTERATO | Scossa orizzontale <=3 px, 220 ms, avviso e motivi sempre visibili | Fedele |

Le icone sono locali, a tratto e decorative: Word, posta, Halley, sessione, riunione e telefonata. L'icona non abilita un sensore. L'anteprima attiva usa solo raw già raccolti; niente nuovo campionamento o classifiche. I dati rilevati, dichiarati e la sintesi hanno etichette oltre al colore.

## Misura reale e simulazione

`tools/benchmark_app.py` istanzia la vera App/Servizio Tk con lettore, orologio e postazione sintetici; tre schermate ogni 12 s e hover ogni 0,5 s. Misura il tempo CPU del processo, working set e memoria privata; confronto movimento ridotto/completo, senza motore LLM attivo. La simulazione imposta profilo RAM 8 GB e un limite reale del Job Object Windows di 8 GB, verificando il successo dell'API. **Non riduce la RAM fisica dell'host e non simula Sangfor, pressione di memoria o latenza VDI.** I numeri non sono un giudizio sulla persona né dati del resoconto.

Misure ripetute sulla vera App Tk da sorgente, con 24/24 campioni in primo piano: PC 12 GB, off/on 2,604/5,201% di un core (incremento 2,597 punti), working set 56,67/56,12 MB. Simulazione 8 GB off/on 3,121/5,208% (incremento 2,087 punti), working set 56,36/56,38 MB. Ripetizione con overlay personalizzato: 2,731/5,599% (incremento 2,868 punti), working set 56,62/56,14 MB. Memoria privata circa 30–31 MB. Stop inattività/background verificato in ogni prova, 284–285 frame in 12 s: meno di 30 fps. Sotto la soglia incrementale di 3–4 punti nelle prove eseguite; campioni brevi sintetici, non stima universale. Il costo PDF e LLM è separato dal costo decorativo. Gli indicatori non rallentano il completamento e si chiudono all'esito effettivo.

Il GIF della galleria è catturato a circa 15 fps dalle finestre Tk, non dal desktop. La sequenza è guidata con dati inventati: mostra schermate, chip e stato di preparazione. PrintWindow non cattura l'alpha del compositor Windows: lo splash è documentato da un PNG e la dissolvenza non è dimostrata dal GIF. Tastiera/focus e scale 100/125/150% sono collaudati con scala applicativa, non modificando il DPI di Windows. Il controllo nativo manuale della sessione non è disponibile: i collaudi installati usano i veri pulsanti Tk mediante il banco strumentato.

## Setup

Inno standard con immagini statiche alle DPI 100/150/200%, testi e pagina finale. Nessun bootstrapper, downloader o animazione artificiale del Setup. Controllare lo spazio disco prima della compilazione dei pacchetti grandi; firma del codice e collaudo senza esclusioni ASR restano compiti di distribuzione dell'Ente.
