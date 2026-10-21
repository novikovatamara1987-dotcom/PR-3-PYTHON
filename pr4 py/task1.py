
A = int(input("Введите целое число A: "))
B = int(input("Введите целое число B (B > A): "))

if A >= B:
    print("Ошибка: должно выполняться A < B")
else:
    for number in range(A, B + 1):
        times = number - A + 1 
        for _ in range(times):
            print(number, end=" ")
    print()
