def multiplicar(args: dict) -> dict:
    a, b = args.get("a"), args.get("b")
    if type(a) is not int or type(b) is not int:
        raise ValueError("a y b deben ser enteros")
    if abs(a) > 10**12 or abs(b) > 10**12:
        raise ValueError("Numeros fuera del rango permitido")
    return {"resultado": a * b}
