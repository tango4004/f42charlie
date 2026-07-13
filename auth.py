import hashlib, random, sys
sys.path.insert(0, '/home/f42charlie/app')
from wordlist import WORDS

def generate_passphrase() -> str:
    # 4 случайных слова из WORDS через пробел
    # каждое слово 4-8 букв (WORDS уже отфильтрован)
    return ' '.join(random.choice(WORDS) for _ in range(4))

def generate_session_id() -> str:
    # слово из WORDS + 4 цифры
    word = random.choice(WORDS)
    digits = str(random.randint(1000, 9999))
    return word + digits

def hash_passphrase(phrase: str) -> str:
    # sha256 hex, lowercase, strip пробелы
    return hashlib.sha256(phrase.strip().lower().encode()).hexdigest()

if __name__ == '__main__':
    phrase = generate_passphrase()
    words = phrase.split()
    assert len(words) == 4, f"expected 4 words, got {len(words)}"
    assert all(4 <= len(w) <= 8 for w in words), f"word length out of range: {words}"
    print(f"passphrase: {phrase}")

    sid = generate_session_id()
    assert len(sid) > 4
    assert sid[-4:].isdigit(), f"last 4 chars not digits: {sid}"
    assert sid[:-4].isalpha(), f"prefix not alpha: {sid}"
    print(f"session_id: {sid}")

    h1 = hash_passphrase(phrase)
    h2 = hash_passphrase(phrase)
    assert h1 == h2, "hash not deterministic"
    assert h1 != hash_passphrase("wrong phrase")
    assert len(h1) == 64
    print(f"hash: {h1[:16]}...")

    print("auth OK")
