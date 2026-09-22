import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Preguntas Migración", page_icon="🛂", layout="centered")

DEFAULT_QUESTIONS = [
    "Una noche perfecta es...",
    "Si les regalan un viaje sorpresa, prefieren...",
    "Ante un conflicto, primero...",
    "Comida para compartir sin pensarlo dos veces:",
    "Un sábado libre ideal empieza con...",
    "Al elegir película, van primero por...",
    "Su forma favorita de mostrar cariño:",
    "Si se mudaran mañana, elegirían...",
    "Su mascota ideal sería...",
    "Lo que más los estresa:",
]

PLAYERS = {"juan": "Juan", "andre": "Andre"}
EMOJI = {"juan": "🔵", "andre": "🟠"}
OTHER = {"juan": "andre", "andre": "juan"}

VERDICTS = [
    (0.9, "Prácticamente la misma persona."),
    (0.7, "Muy en sintonía."),
    (0.5, "Se parecen más de lo que creen."),
    (0.3, "Bastante distintos, y está bien."),
    (0.0, "Polos opuestos — ahí está lo interesante."),
]

PROGRESS_PATH = Path(os.environ.get("CARA_PROGRESS_PATH", Path(__file__).with_name("progress.json")))


def owner_pin():
    env_pin = os.environ.get("CARA_OWNER_PIN", "").strip()
    if env_pin:
        return env_pin
    try:
        return str(st.secrets["OWNER_PIN"]).strip()
    except Exception:
        return ""


def empty_player():
    return {"answers": [], "resume_at": None}


def remote_config():
    token = os.environ.get("CARA_GITHUB_TOKEN", "").strip()
    gist_id = os.environ.get("CARA_GIST_ID", "").strip()
    if token and gist_id:
        return token, gist_id
    try:
        token = str(st.secrets["GITHUB_TOKEN"]).strip()
        gist_id = str(st.secrets["GIST_ID"]).strip()
    except Exception:
        return "", ""
    return token, gist_id


def normalize_store(data):
    if not isinstance(data, dict):
        return None
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions or not all(isinstance(q, str) and q.strip() for q in questions):
        questions = list(DEFAULT_QUESTIONS)

    players = {}
    raw_players = data.get("players") if isinstance(data.get("players"), dict) else {}
    for name in ("juan", "andre"):
        raw = raw_players.get(name) if isinstance(raw_players.get(name), dict) else {}
        answers = raw.get("answers") if isinstance(raw.get("answers"), list) else []
        resume_at = raw.get("resume_at")
        if resume_at is not None:
            try:
                resume_at = int(resume_at)
            except (TypeError, ValueError):
                resume_at = None
        players[name] = {"answers": [str(answer) for answer in answers], "resume_at": resume_at}

    return {
        "questions": questions,
        "using_custom": bool(data.get("using_custom")),
        "players": players,
    }


def gist_request(method, token, gist_id, body=None):
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.github.com/gists/{gist_id}",
        data=payload,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "cara-a-cara",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def load_local():
    if not PROGRESS_PATH.exists():
        return None
    try:
        return normalize_store(json.loads(PROGRESS_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None


def load_remote():
    token, gist_id = remote_config()
    if not token or not gist_id:
        return None
    try:
        payload = gist_request("GET", token, gist_id)
        content = (payload.get("files") or {}).get("progress.json", {}).get("content")
        if not content:
            return None
        return normalize_store(json.loads(content))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, TypeError):
        return None


def load_store():
    remote = load_remote()
    if remote is not None:
        return remote
    return load_local()


def save_local(text):
    try:
        PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = PROGRESS_PATH.with_suffix(".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(PROGRESS_PATH)
        return True
    except OSError:
        return False


def save_remote(text):
    token, gist_id = remote_config()
    if not token or not gist_id:
        return False
    try:
        gist_request("PATCH", token, gist_id, {"files": {"progress.json": {"content": text}}})
        return True
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False


def write_store(questions, using_custom, players):
    text = json.dumps(
        {
            "questions": list(questions),
            "using_custom": bool(using_custom),
            "players": players,
        },
        ensure_ascii=False,
        indent=2,
    )
    token, gist_id = remote_config()
    remote_ok = save_remote(text) if token and gist_id else True
    save_local(text)
    if token and gist_id and not remote_ok:
        st.session_state.save_warning = "No se pudo guardar en línea. El avance quedó solo en esta sesión."
    else:
        st.session_state.save_warning = None


def players_from_state():
    return {
        name: {
            "answers": list(st.session_state.answers[name]),
            "resume_at": st.session_state.resume_at[name],
        }
        for name in ("juan", "andre")
    }


def save_player(player):
    stored = load_store()
    players = stored["players"] if stored else {"juan": empty_player(), "andre": empty_player()}
    players[player] = {
        "answers": list(st.session_state.answers[player]),
        "resume_at": st.session_state.resume_at[player],
    }
    write_store(st.session_state.questions, st.session_state.using_custom, players)


def save_all():
    write_store(st.session_state.questions, st.session_state.using_custom, players_from_state())


def apply_store():
    stored = load_store()
    if stored is None:
        return
    st.session_state.questions = stored["questions"]
    st.session_state.using_custom = stored["using_custom"]
    for name in ("juan", "andre"):
        st.session_state.answers[name] = stored["players"][name]["answers"]
        st.session_state.resume_at[name] = stored["players"][name]["resume_at"]


def has_saved_progress():
    for name in ("juan", "andre"):
        if st.session_state.answers[name] or st.session_state.resume_at[name] is not None:
            return True
    return False


def pin_matches(entered):
    expected = owner_pin()
    return bool(expected) and entered.strip() == expected


# ---------------------------------------------------------------- state ----

def init_state():
    defaults = {
        "screen": "menu",              # menu | quiz | done | results
        "questions": DEFAULT_QUESTIONS,
        "using_custom": False,
        "answers": {"juan": [], "andre": []},
        "active_player": None,
        "q_index": 0,
        "compare_warning": None,
        "qset_message": None,
        "confirm_retake": None,        # "juan" | "andre" | None
        "confirm_reset": False,
        "resume_at": {"juan": None, "andre": None},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    for player in ("juan", "andre"):
        st.session_state.resume_at.setdefault(player, None)
    if not st.session_state.get("progress_loaded"):
        apply_store()
        st.session_state.progress_loaded = True

    questions = st.session_state.questions
    if questions and isinstance(questions[0], dict):
        st.session_state.questions = [q["q"] for q in questions]
        st.session_state.answers = {"juan": [], "andre": []}
        clear_answer_keys()


def is_complete(player):
    answers = st.session_state.answers[player]
    return len(answers) >= len(st.session_state.questions) and all(str(a).strip() for a in answers)


def both_complete():
    return is_complete("juan") and is_complete("andre")


def clear_answer_keys(player=None):
    prefix = f"answer_{player}_" if player else "answer_"
    for key in list(st.session_state.keys()):
        if key.startswith(prefix):
            del st.session_state[key]


def parse_questions_txt(text):
    """One question per line. Anything after a | is ignored."""
    questions = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        question = line.split("|", 1)[0].strip()
        if question:
            questions.append(question)
    return questions


def same_answer(a, b):
    def norm(value):
        return " ".join(str(value).strip().lower().split())

    return norm(a) == norm(b)


def match_summary():
    questions = st.session_state.questions
    ans_juan = st.session_state.answers["juan"]
    ans_andre = st.session_state.answers["andre"]
    matches = sum(1 for i in range(len(questions)) if same_answer(ans_juan[i], ans_andre[i]))
    ratio = matches / len(questions) if questions else 0
    verdict = next(text for threshold, text in VERDICTS if ratio >= threshold)
    return matches, verdict


def build_answers_txt():
    questions = st.session_state.questions
    ans_juan = st.session_state.answers["juan"]
    ans_andre = st.session_state.answers["andre"]
    matches, verdict = match_summary()
    lines = [
        "Cara a Cara",
        f"{matches}/{len(questions)} respuestas iguales",
        verdict,
        "",
    ]
    for i, question in enumerate(questions):
        lines.append(f"{i + 1}. {question}")
        lines.append(f"Juan: {ans_juan[i]}")
        lines.append(f"Andre: {ans_andre[i]}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_download():
    st.download_button(
        "Descargar respuestas (.txt)",
        data=build_answers_txt(),
        file_name="cara-a-cara.txt",
        mime="text/plain",
        use_container_width=True,
        key="download_answers",
    )


# --------------------------------------------------------------- screens ----

def start_quiz(player):
    clear_answer_keys(player)
    st.session_state.answers[player] = []
    st.session_state.resume_at[player] = 0
    st.session_state.q_index = 0
    st.session_state.active_player = player
    st.session_state.screen = "quiz"
    save_player(player)


def resume_quiz(player):
    n = len(st.session_state.questions)
    idx = st.session_state.resume_at[player]
    if idx is None:
        idx = 0
    st.session_state.q_index = min(max(idx, 0), n - 1)
    st.session_state.active_player = player
    st.session_state.screen = "quiz"


def reset_all_progress():
    st.session_state.answers = {"juan": [], "andre": []}
    st.session_state.resume_at = {"juan": None, "andre": None}
    st.session_state.active_player = None
    st.session_state.q_index = 0
    st.session_state.screen = "menu"
    st.session_state.confirm_retake = None
    st.session_state.confirm_reset = False
    clear_answer_keys()
    save_all()


def render_menu():
    n = len(st.session_state.questions)
    st.title("Cara × Cara")
    st.caption(f"{n} preguntas cada quien, sin ver las respuestas del otro. "
               "Pausar guarda el lugar: si cierran la página o vuelven otro día, siguen en la misma pregunta.")
    if st.session_state.get("save_warning"):
        st.warning(st.session_state.save_warning)

    col_juan, col_andre = st.columns(2)
    for col, key in zip((col_juan, col_andre), ("juan", "andre")):
        with col:
            done = is_complete(key)
            paused_at = st.session_state.resume_at[key]
            if done:
                label = f"{EMOJI[key]} {PLAYERS[key]} ✅"
            elif paused_at is not None:
                label = f"{EMOJI[key]} {PLAYERS[key]} · continuar"
            else:
                label = f"{EMOJI[key]} {PLAYERS[key]}"
            if st.button(label, key=f"start_{key}", use_container_width=True):
                if done:
                    st.session_state.confirm_retake = key
                elif paused_at is not None:
                    resume_quiz(key)
                    st.rerun()
                else:
                    start_quiz(key)
                    st.rerun()
            if not done and paused_at is not None:
                st.caption(f"Pausado en la pregunta {paused_at + 1} de {n}")

    if st.session_state.confirm_retake:
        key = st.session_state.confirm_retake
        st.warning(f"{PLAYERS[key]} ya respondió. Para borrar esas respuestas hace falta la clave.")
        pin = st.text_input("Clave", type="password", key="retake_pin")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Borrar y volver a responder", key="confirm_yes", use_container_width=True):
                if pin_matches(pin):
                    st.session_state.confirm_retake = None
                    start_quiz(key)
                    st.rerun()
                else:
                    st.error("Clave incorrecta.")
        with c2:
            if st.button("Cancelar", key="confirm_no", use_container_width=True):
                st.session_state.confirm_retake = None
                st.rerun()

    st.divider()
    if st.button("Comparar respuestas", type="primary", use_container_width=True):
        if both_complete():
            st.session_state.screen = "results"
            st.session_state.compare_warning = None
            st.rerun()
        else:
            missing = [PLAYERS[k] for k in ("juan", "andre") if not is_complete(k)]
            if len(missing) == 2:
                st.session_state.compare_warning = f"Juan y Andre todavía no responden sus {n} preguntas."
            else:
                st.session_state.compare_warning = f"Falta que {missing[0]} termine sus {n} preguntas antes de comparar."

    if st.session_state.compare_warning:
        st.info(st.session_state.compare_warning)

    if st.button("Reiniciar test", use_container_width=True):
        st.session_state.confirm_reset = True

    if st.session_state.confirm_reset:
        st.warning("Esto borra las respuestas de Juan y Andre.")
        pin = st.text_input("Clave", type="password", key="reset_menu_pin")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Borrar y reiniciar", key="reset_menu_yes", use_container_width=True):
                if pin_matches(pin):
                    st.session_state.confirm_reset = False
                    reset_all_progress()
                    st.rerun()
                else:
                    st.error("Clave incorrecta.")
        with c2:
            if st.button("Cancelar", key="reset_menu_no", use_container_width=True):
                st.session_state.confirm_reset = False
                st.rerun()

    if both_complete():
        render_download()

    st.divider()
    with st.expander("Usar mis propias preguntas (.txt)"):
        st.caption("Una pregunta por línea. Cada quien escribe su respuesta con sus propias palabras.")
        st.code("¿Playa o montaña?\n¿Qué harían un sábado libre?", language=None)

        uploaded = st.file_uploader("Sube tu archivo .txt", type="txt", key="qset_uploader")
        if uploaded is not None:
            text = uploaded.read().decode("utf-8", errors="ignore")
            parsed = parse_questions_txt(text)
            if len(parsed) < 2:
                st.error("No se pudo leer el archivo. Escribe al menos 2 preguntas, una por línea.")
            elif has_saved_progress():
                st.warning("Hay respuestas guardadas. La clave es necesaria para cambiar las preguntas.")
                pin = st.text_input("Clave", type="password", key="replace_questions_pin")
                if st.button("Usar estas preguntas"):
                    if pin_matches(pin):
                        apply_question_set(parsed, custom=True)
                        st.rerun()
                    else:
                        st.error("Clave incorrecta.")
            else:
                apply_question_set(parsed, custom=True)
                st.success(f"Cargadas {len(parsed)} preguntas personalizadas desde “{uploaded.name}”.")

        if st.session_state.using_custom:
            if st.button("Volver a las preguntas originales"):
                if has_saved_progress():
                    st.session_state.confirm_restore_original = True
                else:
                    apply_question_set(DEFAULT_QUESTIONS, custom=False)
                    st.rerun()
            if st.session_state.get("confirm_restore_original"):
                pin = st.text_input("Clave", type="password", key="restore_original_pin")
                if st.button("Confirmar y borrar respuestas"):
                    if pin_matches(pin):
                        st.session_state.confirm_restore_original = False
                        apply_question_set(DEFAULT_QUESTIONS, custom=False)
                        st.rerun()
                    else:
                        st.error("Clave incorrecta.")


def apply_question_set(questions, custom):
    st.session_state.questions = list(questions)
    st.session_state.using_custom = custom
    st.session_state.answers = {"juan": [], "andre": []}
    st.session_state.resume_at = {"juan": None, "andre": None}
    clear_answer_keys()
    save_all()


def render_quiz():
    player = st.session_state.active_player
    questions = st.session_state.questions
    idx = st.session_state.q_index
    question = questions[idx]
    answer_key = f"answer_{player}_{idx}"
    saved = st.session_state.answers[player]
    if answer_key not in st.session_state and idx < len(saved):
        st.session_state[answer_key] = saved[idx]

    st.subheader(f"{EMOJI[player]} Turno de {PLAYERS[player]}")
    st.progress(idx / len(questions))
    st.caption(f"Pregunta {idx + 1} de {len(questions)}")

    st.markdown(f"### {question}")
    st.caption("Escribe lo que quieras.")
    answer = st.text_area(
        "Tu respuesta",
        key=answer_key,
        label_visibility="collapsed",
        placeholder="Tu respuesta...",
        height=120,
    )

    def save_current():
        answers = st.session_state.answers[player]
        if len(answers) <= idx:
            answers.extend([""] * (idx + 1 - len(answers)))
        answers[idx] = answer.strip()

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("Atrás", disabled=(idx == 0), use_container_width=True):
            save_current()
            st.session_state.q_index -= 1
            st.session_state.resume_at[player] = st.session_state.q_index
            save_player(player)
            st.rerun()
    with col_next:
        is_last = idx == len(questions) - 1
        if st.button("Terminar" if is_last else "Siguiente",
                      type="primary", disabled=not answer.strip(), use_container_width=True):
            save_current()
            if is_last:
                st.session_state.resume_at[player] = None
                st.session_state.screen = "done"
            else:
                st.session_state.q_index += 1
                st.session_state.resume_at[player] = st.session_state.q_index
            save_player(player)
            st.rerun()

    if st.button("Pausar", use_container_width=True):
        save_current()
        st.session_state.resume_at[player] = idx
        save_player(player)
        st.session_state.screen = "menu"
        st.rerun()


def render_done():
    player = st.session_state.active_player
    other = OTHER[player]

    st.success(f"¡Listo, {PLAYERS[player]}!")
    if is_complete(other):
        st.write("Tus respuestas quedaron guardadas. Ya pueden comparar o descargar el archivo.")
        render_download()
    else:
        st.write(f"Tus respuestas quedaron guardadas. Cuando {PLAYERS[other]} también termine, "
                 f"vuelvan aquí y toquen **Comparar respuestas**.")

    if st.button("Volver al menú", type="primary", use_container_width=True):
        st.session_state.screen = "menu"
        st.rerun()


def render_results():
    questions = st.session_state.questions
    ans_juan = st.session_state.answers["juan"]
    ans_andre = st.session_state.answers["andre"]
    matches, verdict = match_summary()

    st.markdown(f"<h1 style='text-align:center'>{matches}/{len(questions)}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center'>respuestas iguales</p>", unsafe_allow_html=True)
    st.markdown(f"<h3 style='text-align:center'>{verdict}</h3>", unsafe_allow_html=True)

    st.divider()

    for i, question in enumerate(questions):
        match = same_answer(ans_juan[i], ans_andre[i])
        with st.container(border=True):
            st.caption(question)
            c1, c2, c3 = st.columns([5, 1, 5])
            with c1:
                st.markdown(f"**{EMOJI['juan']} Juan**")
                st.text(ans_juan[i])
            c2.markdown("<p style='text-align:center'>✅</p>" if match else "<p style='text-align:center'>❌</p>",
                        unsafe_allow_html=True)
            with c3:
                st.markdown(f"**Andre {EMOJI['andre']}**")
                st.text(ans_andre[i])

    st.divider()
    render_download()
    with st.expander("Detener el test y borrar respuestas"):
        st.caption("Solo con la clave se borra el avance de Juan y Andre.")
        pin = st.text_input("Clave", type="password", key="reset_all_pin")
        if st.button("Borrar todo y empezar de nuevo", use_container_width=True):
            if pin_matches(pin):
                reset_all_progress()
                st.rerun()
            else:
                st.error("Clave incorrecta.")


# ----------------------------------------------------------------- main ----

init_state()

screen = st.session_state.screen
if screen == "menu":
    render_menu()
elif screen == "quiz":
    render_quiz()
elif screen == "done":
    render_done()
elif screen == "results":
    render_results()
