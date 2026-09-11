from correios_rastreio import rastrear

# Utilize um código de rastreio real ou válido para teste
codigo_teste = "LB123456789BR"

print(f"Buscando informações para: {codigo_teste}...")

try:
    resultado = rastrear(codigo_teste)
    if resultado:
        print("\n✅ Sucesso! Último status retornado:")
        print(f"Status: {resultado[0].get('status')}")
        print(f"Data/Hora: {resultado[0].get('data')} {resultado[0].get('hora')}")
    else:
        print("\n⚠️ Nenhum evento encontrado para este código.")
except Exception as e:
    print(f"\n❌ Erro ao consultar: {e}")
