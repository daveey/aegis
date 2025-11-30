import asana
import inspect

print("SectionsApi methods:")
for m in dir(asana.SectionsApi):
    if not m.startswith("_"):
        print(f"  {m}")

print("\nProjectsApi.add_custom_field_setting_for_project signature:")
try:
    print(inspect.signature(asana.ProjectsApi.add_custom_field_setting_for_project))
except Exception as e:
    print(e)
