async def scan_orion_devices(hass, mqtt_client):
    """Сканирование Orion адресов 1-127 (синхронно)"""
    
    if hass.data[DOMAIN].get("scan_in_progress"):
        return
    
    hass.data[DOMAIN]["scan_in_progress"] = True
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, "Сканирование Orion: подготовка...")
    _LOGGER.info("Начало сканирования Orion (адреса 1-127)")
    
    for addr in range(1, 128):
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование Orion: адрес {addr} из 127")
        command = f"{addr};6;0;13;0;0"
        response = await mqtt_client.send_command_and_wait(command, expected_rsp_type=RSP_ORION, timeout=5.0)
        
        if response:
            await process_orion_response(hass, response, addr)
        
        await asyncio.sleep(0.1)
    
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование Orion завершено. Найдено: {len(hass.data[DOMAIN]['orion_devices'])}")
    _LOGGER.info(f"Сканирование Orion завершено. Найдено: {len(hass.data[DOMAIN]['orion_devices'])}")
    
    for kdl_addr in hass.data[DOMAIN]["kdl_addresses"]:
        await scan_dpls_line(hass, mqtt_client, kdl_addr)
    
    orion_count = len(hass.data[DOMAIN]["orion_devices"])
    dpls_count = len(hass.data[DOMAIN]["dpls_devices"])
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование завершено. Orion: {orion_count}, DPLS: {dpls_count}")
    _LOGGER.info(f"Сканирование завершено. Orion: {orion_count}, DPLS: {dpls_count}")
    
    hass.data[DOMAIN]["scan_in_progress"] = False


async def scan_dpls_line(hass, mqtt_client, kdl_address):
    """Синхронное сканирование DPLS линии (адреса 1-127)"""
    
    _LOGGER.info(f"Сканирование DPLS для КДЛ {kdl_address}")
    async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование DPLS: КДЛ {kdl_address}")
    
    for dpls_addr in range(1, 128):
        async_dispatcher_send(hass, SIGNAL_STATUS_UPDATE, f"Сканирование DPLS: КДЛ {kdl_address}, адрес {dpls_addr} из 127")
        command = f"{kdl_address};6;0;57;{dpls_addr};1"
        
        response = await mqtt_client.send_command_and_wait(command, expected_rsp_type=RSP_DPLS, timeout=5.0)
        
        if response:
            await process_dpls_response(hass, response, kdl_address, dpls_addr)
        
        await asyncio.sleep(0.1)


async def process_orion_response(hass, response, expected_addr):
    """Обработка ответа на команду 13"""
    parts = response.strip().split()
    if len(parts) < 8:
        return
    
    try:
        address = int(parts[0])
        if address != expected_addr:
            return
        
        device_type = int(parts[3])
        byte4 = int(parts[4])
        byte5 = int(parts[5])
        devVer = byte4 | (byte5 << 8)
        major = devVer // 100
        minor = devVer % 100
        version = f"{major}.{minor:02d}"
        
        device_name = ORION_DEVICE_TYPES.get(device_type, f"Тип {device_type}")
        
        _LOGGER.info(f"Найден Orion: адрес {address} -> {device_name}")
        
        orion_devices = hass.data[DOMAIN]["orion_devices"]
        
        if address not in orion_devices:
            orion_devices[address] = {
                "name": device_name,
                "type_code": device_type,
                "firmware": version,
            }
            async_dispatcher_send(hass, f"{DOMAIN}_new_orion_device", address, orion_devices[address])
            
            if device_type == 9 and address not in hass.data[DOMAIN]["kdl_addresses"]:
                hass.data[DOMAIN]["kdl_addresses"].append(address)
                _LOGGER.info(f"Добавлен КДЛ адрес {address}")
    except (ValueError, IndexError) as e:
        _LOGGER.error(f"Ошибка парсинга Orion: {e}")


async def process_dpls_response(hass, response, kdl_address, requested_addr):
    """Обработка ответа на команду 57"""
    parts = response.strip().split()
    if len(parts) < 5:
        return
    
    try:
        device_exists = int(parts[3])
        dpls_type = int(parts[4])
        
        if device_exists != 0 and dpls_type != 0:
            device_name = DPLS_DEVICE_TYPES.get(dpls_type, f"Тип {dpls_type}")
            
            _LOGGER.info(f"Найден DPLS: КДЛ {kdl_address}, DPLS адрес {requested_addr}, тип {device_name}")
            
            dpls_devices = hass.data[DOMAIN]["dpls_devices"]
            device_key = f"{kdl_address}_{requested_addr}"
            
            if device_key not in dpls_devices:
                dpls_devices[device_key] = {
                    "name": device_name,
                    "type_code": dpls_type,
                    "kdl_address": kdl_address,
                    "dpls_address": requested_addr,
                    "status_code": None,
                    "status_text": None,
                }
                async_dispatcher_send(hass, f"{DOMAIN}_new_dpls_device", device_key, dpls_devices[device_key])
    except (ValueError, IndexError) as e:
        _LOGGER.error(f"Ошибка парсинга DPLS: {e}")
