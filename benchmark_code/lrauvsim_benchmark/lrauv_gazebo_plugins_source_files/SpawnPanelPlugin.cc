/*
 * Copyright (C) 2021 Open Source Robotics Foundation
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */

/*
 * Development of this module has been funded by the Monterey Bay Aquarium
 * Research Institute (MBARI) and the David and Lucile Packard Foundation
 */

#include "SpawnPanelPlugin.hh"
#include <gz/common/Console.hh>
#include <gz/plugin/Register.hh>

#include <gz/gui/Application.hh>
#include <gz/gui/Conversions.hh>
#include <gz/gui/GuiEvents.hh>
#include <gz/gui/MainWindow.hh>

#include <gz/sim/Util.hh>
#include <gz/sim/World.hh>

#include <cstdlib>  // For rand() and srand()

namespace tethys
{

SpawnPanel::SpawnPanel()
{
  gz::gui::App()->Engine()->rootContext()->setContextProperty(
    "SpawnPanel", this);

  this->pub = this->node.Advertise<lrauv_gazebo_plugins::msgs::LRAUVInit>(
      "/lrauv/init");
}

SpawnPanel::~SpawnPanel()
{

}

void SpawnPanel::LoadConfig(const tinyxml2::XMLElement *_pluginElem)
{
  if (this->title.empty())
    this->title = "Spawn LRAUV Panel";

  gz::gui::App()->findChild<
    gz::gui::MainWindow *>()->installEventFilter(this);
}

void SpawnPanel::Spawn(
  double lattitude, double longitude, double depth, int commsId, QString name)
{
  if (this->acousticIds.count(commsId) > 0)
  {
    gzerr << "Comms ID [" << commsId << "] already exists.\n";
    return;
  }

  auto vehName = name.toStdString();
  if (this->modelNames.count(vehName) > 0)
  {
    gzerr << "Model name [" << vehName << "] already exists.\n";
    return;
  }

  lrauv_gazebo_plugins::msgs::LRAUVInit msg;
  msg.set_initlat_(lattitude);
  msg.set_initlon_(longitude);
  msg.set_initz_(depth);
  msg.set_acommsaddress_(commsId);
  msg.mutable_id_()->set_data(vehName);
  this->pub.Publish(msg);

  this->acousticIds.insert(commsId);
  this->modelNames.insert(vehName);
}


void SpawnPanel::SpawnMulti(
  double baseLat, double baseLon, double baseDepth,
  int baseCommsId, int nbLRAUV, QString namePrefix)
{
  for (int i = 0; i < nbLRAUV; ++i)
  {
    int commsId = baseCommsId + i;
    std::string vehName = namePrefix.toStdString() + std::to_string(i);

    if (this->acousticIds.count(commsId) > 0)
    {
      gzerr << "Comms ID [" << commsId << "] already exists. Skipping.\n";
      continue;
    }

    if (this->modelNames.count(vehName) > 0)
    {
      gzerr << "Model name [" << vehName << "] already exists. Skipping.\n";
      continue;
    }

    // Random offset for latitude, longitude, and depth
    double lat = baseLat + ((rand() % 100) - 50) * 0.0001;  // ±0.005 deg
    double lon = baseLon + ((rand() % 100) - 50) * 0.0001;
    double depth = baseDepth + ((rand() % 100) - 50) * 0.1;  // ±5 meters

    lrauv_gazebo_plugins::msgs::LRAUVInit msg;
    msg.set_initlat_(lat);
    msg.set_initlon_(lon);
    msg.set_initz_(depth);
    msg.set_acommsaddress_(commsId);
    msg.mutable_id_()->set_data(vehName);

    this->pub.Publish(msg);
    this->acousticIds.insert(commsId);
    this->modelNames.insert(vehName);

    gzmsg << "Spawned " << vehName << " at ("
          << lat << ", " << lon << ", " << depth
          << ") with commsId " << commsId << "\n";
  }
}



void SpawnPanel::Update(const gz::sim::UpdateInfo &,
  gz::sim::EntityComponentManager &_ecm)
{
}

}

// Register this plugin
GZ_ADD_PLUGIN(tethys::SpawnPanel,
                    gz::gui::Plugin)
