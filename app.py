from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, join_room, emit
import pandas as pd
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'siber_guvenlik_oyunu_anahtar'
socketio = SocketIO(app)

# Excel verisini yükle
df = pd.read_excel("siber_guvenlik_oyunu_gercekci_maliyet.xlsx")
saldiri_turleri = df["Saldırı"].unique().tolist()

# Oyun odaları
rooms = {}

@app.route('/')
def index():
    return render_template('lobby.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    player_name = request.form['player_name']
    tur_sayisi = int(request.form['tur_sayisi'])  # Yeni alanı al

    room_id = str(uuid.uuid4())[:6]
    rooms[room_id] = {
        'players': {'red': player_name},
        'state': {
            'tur': 1,
            'maksimum_tur': tur_sayisi,  # Yeni bilgi eklendi
            'blue_butce': 70000,
            'blue_puan': 0,
            'red_puan': 0,
            'itibar': "Yüksek"
        }
    }
    return redirect(url_for('game_room', room_id=room_id, role='red'))
@app.route('/join_room', methods=['POST'])
def join_room_route():
    player_name = request.form['player_name']
    room_id = request.form['room_id']
    if room_id in rooms and 'blue' not in rooms[room_id]['players']:
        rooms[room_id]['players']['blue'] = player_name
        return redirect(url_for('game_room', room_id=room_id, role='blue'))
    return "Oda bulunamadı veya dolu", 400

@app.route('/room/<room_id>/<role>')
def game_room(room_id, role):
    if role == 'red':
        return render_template('red_select.html', room_id=room_id, role=role, saldirilar=saldiri_turleri)
    else:
        return render_template('blue_wait.html', room_id=room_id, role=role)

@app.route('/result/<room_id>')
def result(room_id):
    state = rooms[room_id]['state']
    return render_template('result.html',
                           blue_puan=state['blue_puan'],
                           red_puan=state['red_puan'],
                           blue_butce=state['blue_butce'],
                           itibar=state['itibar'],
                           tur=state['maksimum_tur'],
                           maksimum_tur=state['maksimum_tur'])

@app.route('/tur_sonucu/<room_id>/<role>')
def tur_sonucu(room_id, role):
    state = rooms[room_id]['state']
    return render_template('tur_sonucu.html',
                           room_id=room_id,
                           role=role,
                           tur=state['tur'],
                           maksimum_tur=state['maksimum_tur'],
                           oyun_bitti_mi=state.get('oyun_bitti_mi', False),
                           dogru_onlemler=state.get('dogru_onlemler', []),
                           yanlis_onlemler=state.get('yanlis_onlemler', []),
                           blue_puan=state['blue_puan'],
                           red_puan=state['red_puan'],
                           blue_butce=state['blue_butce'],
                           itibar=state['itibar'],
                           ek_maliyet=state.get('ek_maliyet', 0),
                           genel_mesaj=state.get('genel_mesaj', ''))

@app.route('/blue_defense/<room_id>/<role>')
def blue_defense(room_id, role):
    state = rooms[room_id]['state']
    attack = state.get('last_attack', None)

    if not attack:
        return "Henüz saldırı seçilmedi", 400

    # Doğru önlemler
    dogru_onlemler = df[df["Saldırı"] == attack]["Savunma Önlemleri"].tolist()

    # Yanlış önlemler
    tum_onlemler = df["Savunma Önlemleri"].unique().tolist()
    yanlislar = [o for o in tum_onlemler if o not in dogru_onlemler]
    import random
    rastgele_yanlislar = random.sample(yanlislar, min(3, len(yanlislar)))

    # Karıştırılmış liste
    onlemler = dogru_onlemler + rastgele_yanlislar
    random.shuffle(onlemler)

    # Maliyetleri eşleştir
    onlem_verileri = []
    for onlem in onlemler:
        satir = df[df["Savunma Önlemleri"] == onlem].iloc[0]
        onlem_verileri.append({
            "ad": onlem,
            "maliyet": int(satir["Önlem Maliyeti"])
        })

    return render_template('blue_defense.html',
                           room_id=room_id,
                           role=role,
                           belirtiler=df[df["Saldırı"] == attack]["Belirtiler"].iloc[0],
                           onlemler=onlem_verileri,
                           butce=state['blue_butce'],
                           tur=state['tur'])


@app.route('/red_wait/<room_id>')
def red_wait(room_id):
    return render_template('red_wait.html', room_id=room_id)

@socketio.on('join')
def handle_join(data):
    join_room(data['room'])
    emit('player_joined', data, room=data['room'])

@socketio.on('red_attack')
def handle_red_attack(data):
    room = data['room']
    attack = data['attack']

    rooms[room]['state']['last_attack'] = attack

    belirtiler = df[df["Saldırı"] == attack]["Belirtiler"].iloc[0]
    onlemler = df[df["Saldırı"] == attack]["Savunma Önlemleri"].tolist()

    emit('attack_selected', {
        'attack': attack,
        'belirtiler': belirtiler,
        'onlemler': onlemler

   }, room=room)
from flask import request
@socketio.on('blue_defense')
def handle_blue_defense(data):
    room = data['room']
    secimler = data['defense']
    room_state = rooms[room]['state']
    attack = room_state.get('last_attack')
    dogru_onlem_listesi = df[df["Saldırı"] == attack]["Savunma Önlemleri"].tolist()

    toplam_oncelik = 0
    dogru_onlemler = []
    yanlis_onlemler = []
    ek_maliyet = 0

    if not secimler:
        room_state['red_puan'] += 12
        room_state['blue_butce'] -= 20000
        room_state['itibar'] = "Çok Düşük"
        genel_mesaj = "⏰ Süre doldu! Savunma yapılmadı. Red Team +12 puan. Blue Team -$20.000 ve itibar kaybı."

        room_state['dogru_onlemler'] = []
        room_state['yanlis_onlemler'] = []
        room_state['ek_maliyet'] = 20000
        room_state['genel_mesaj'] = genel_mesaj

    else:
        for secim in secimler:
            satir = df[df["Savunma Önlemleri"] == secim].iloc[0]
            maliyet = int(satir["Önlem Maliyeti"])
            yanlis_kayip = int(str(satir["Yanlış Seçim Maliyet Kaybı"]).replace("$", "").replace(".", "").strip())
            itibar_kaybi = satir["Yanlış Seçim İtibar Kaybı"]
            oncelik = int(satir["Öncelik"])

            if room_state['blue_butce'] >= maliyet:
                room_state['blue_butce'] -= maliyet

                if secim in dogru_onlem_listesi:
                    dogru_onlemler.append(secim)
                    toplam_oncelik += oncelik
                else:
                    yanlis_onlemler.append(secim)
                    room_state['blue_butce'] -= yanlis_kayip
                    ek_maliyet += yanlis_kayip

                    if itibar_kaybi == "Çok Yüksek":
                        room_state['itibar'] = "Çok Düşük"
                    elif itibar_kaybi == "Yüksek":
                        room_state['itibar'] = "Düşük"
                    elif itibar_kaybi == "Orta" and room_state['itibar'] not in ["Çok Düşük", "Düşük"]:
                        room_state['itibar'] = "Orta"
                    elif itibar_kaybi == "Düşük" and room_state['itibar'] == "Yüksek":
                        room_state['itibar'] = "Orta"

        if toplam_oncelik >= 3:
            room_state['blue_puan'] += 15
            genel_mesaj = "🎯 Kritik önlem başarıyla uygulandı! +15 puan"
        elif toplam_oncelik == 2:
            room_state['blue_puan'] += 8
            room_state['red_puan'] += 3
            genel_mesaj = "⚠️ Kısmi savunma! +8 puan. Red Team +3 puan"
        elif toplam_oncelik == 1:
            room_state['blue_puan'] += 3
            room_state['red_puan'] += 5
            genel_mesaj = "⚠️ Zayıf savunma! +3 puan. Red Team +5 puan"
        else:
            room_state['red_puan'] += 10
            genel_mesaj = "❌ Savunma başarısız! Red Team +10 puan"

        room_state['dogru_onlemler'] = dogru_onlemler
        room_state['yanlis_onlemler'] = yanlis_onlemler
        room_state['ek_maliyet'] = ek_maliyet
        room_state['genel_mesaj'] = genel_mesaj

    room_state['tur'] += 1
    room_state['oyun_bitti_mi'] = room_state['tur'] > room_state['maksimum_tur']

    emit('defense_result', {'next_url': f"/tur_sonucu/{room}/blue"}, to=request.sid)
    emit('defense_result', {'next_url': f"/tur_sonucu/{room}/red"}, room=room, skip_sid=request.sid)
if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)