
a = int(input("Введите первое натуральное число: "))
b = int(input("Введите второе натуральное число: "))

if a <= 0 or b <= 0:
    print("Ошибка: числа должны быть натуральными")
else:
    x, y = a, b
    while x != 0 and y != 0:
        if x > y:
            x = x - y
        else:
            y = y - x
    gcd = x + y
    print(f"НОД({a}, {b}) = {gcd}")
