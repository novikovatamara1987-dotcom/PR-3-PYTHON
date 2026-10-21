
import math


def series_sum(x, eps):
    """Сумма ряда с точностью eps. Возвращает (сумма, число слагаемых)."""
    n = 0
    fact = 1                 
    power = 1.0              
    total = 0.0
    while True:
        term = (2 * n + 1) / fact * power
        total += term
        n += 1
        if abs(term) < eps: 
            break
        fact *= n
        power *= x * x
    return total, n


x = float(input("Введите x: "))
eps = float(input("Введите погрешность e (например 0.0001): "))

left = (1 + 2 * x ** 2) * math.exp(x ** 2)
right, n = series_sum(x, eps)

print(f"Левая часть  (1+2x^2)*e^(x^2) = {left:.10f}")
print(f"Сумма ряда                    = {right:.10f}")
print(f"Разность                      = {abs(left - right):.3e}")
print(f"Число слагаемых n             = {n}")

print("\n   x      слагаемых    |разность|")
for xv in (0.1, 0.5, 1, 2, 3):
    s, k = series_sum(xv, eps)
    l = (1 + 2 * xv ** 2) * math.exp(xv ** 2)
    print(f"{xv:5}   {k:8d}    {abs(l - s):.3e}")
