import sounddevice as sd


def get_output_devices():
    try:
        devices = sd.query_devices()
        output_devices = []

        for i, dev in enumerate(devices):
            if dev['max_output_channels'] > 0:
                name = f"{i} - {dev['name']}"
                output_devices.append((name, i))

        if not output_devices:
            return [("0 - Default", 0)]

        return output_devices

    except Exception as e:
        print("Error dispositivos:", e)
        return [("0 - Default", 0)]